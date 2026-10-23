import calendar
from datetime import date

from contas.models import PerfilAluno
from contas.models import Usuario
from django.db import IntegrityError, transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from .models import (
    Conquista,
    ConquistaConcedida,
    Missao,
    MissaoAluno,
    NotificacaoAluno,
    Patente,
    QuizTentativa,
    ResultadoRanking,
    XPPeriodo,
    XPRegra,
    XPTransacao,
)


def notificar_novidade_alunos(*, tipo, titulo, mensagem, destino, serie=""):
    alunos = Usuario.objects.filter(papel=Usuario.Papel.ALUNO)
    if serie:
        alunos = alunos.filter(perfil_aluno__serie=serie)
    agora = timezone.now()
    NotificacaoAluno.objects.bulk_create(
        [
            NotificacaoAluno(
                usuario_id=aluno_id,
                tipo=tipo,
                titulo=titulo[:160],
                mensagem=mensagem[:250],
                destino=destino,
                criada_em=agora,
            )
            for aluno_id in alunos.values_list("pk", flat=True)
        ],
        batch_size=500,
    )


def _periodos_do_dia(dia=None):
    dia = dia or timezone.localdate()
    inicio_temporada = dia.replace(day=1)
    fim_temporada = dia.replace(
        day=calendar.monthrange(dia.year, dia.month)[1]
    )
    temporada, _ = XPPeriodo.objects.get_or_create(
        tipo=XPPeriodo.Tipo.TEMPORADA,
        chave=dia.strftime("%Y-%m"),
        defaults={"inicio": inicio_temporada, "fim": fim_temporada},
    )
    periodo_anual, _ = XPPeriodo.objects.get_or_create(
        tipo=XPPeriodo.Tipo.ANUAL,
        chave=str(dia.year),
        defaults={"inicio": date(dia.year, 1, 1), "fim": date(dia.year, 12, 31)},
    )
    return temporada, periodo_anual


def conceder_xp(usuario, atividade, referencia, descricao, dia=None):
    """Registra XP de uma atividade validada uma única vez por referência."""
    if usuario.papel != "aluno":
        return None

    referencia = str(referencia)
    existente = XPTransacao.objects.filter(
        usuario=usuario, origem=atividade, referencia=referencia
    ).first()
    if existente:
        return existente

    regra = XPRegra.objects.filter(atividade=atividade, ativa=True).first()
    if regra is None:
        return None

    temporada, periodo_anual = _periodos_do_dia(dia)
    if temporada.fechado or periodo_anual.fechado:
        return None

    try:
        with transaction.atomic():
            return XPTransacao.objects.create(
                usuario=usuario,
                regra=regra,
                origem=atividade,
                referencia=referencia,
                atividade=descricao[:160],
                xp=regra.xp,
                temporada=temporada,
                periodo_anual=periodo_anual,
                validada=True,
            )
    except IntegrityError:
        # Outra requisição pode ter registrado a mesma referência em paralelo.
        return XPTransacao.objects.get(
            usuario=usuario, origem=atividade, referencia=referencia
        )


def resumo_xp(usuario, dia=None):
    temporada, periodo_anual = _periodos_do_dia(dia)
    transacoes = XPTransacao.objects.filter(usuario=usuario, validada=True)
    total_temporada = transacoes.filter(temporada=temporada).aggregate(
        total=Sum("xp")
    )["total"] or 0
    total_anual = transacoes.filter(periodo_anual=periodo_anual).aggregate(
        total=Sum("xp")
    )["total"] or 0
    total_vitalicio = transacoes.aggregate(total=Sum("xp"))["total"] or 0
    return {
        "xp_temporada": total_temporada,
        "xp_anual": total_anual,
        "xp_vitalicio": total_vitalicio,
        "temporada": temporada,
        "periodo_anual": periodo_anual,
    }


def fechar_periodo_ranking(periodo, hoje=None):
    """Congela o ranking de um período concluído e salva apelidos e pontuações."""
    hoje = hoje or timezone.localdate()
    if periodo.fim >= hoje:
        raise ValueError("Só é possível fechar um período que já terminou.")

    with transaction.atomic():
        periodo = type(periodo).objects.select_for_update().get(pk=periodo.pk)
        if periodo.fechado:
            return list(periodo.resultados_ranking.all())

        campo_periodo = (
            "temporada" if periodo.tipo == XPPeriodo.Tipo.TEMPORADA else "periodo_anual"
        )
        pontos = dict(
            XPTransacao.objects.filter(
                **{campo_periodo: periodo}, validada=True
            )
            .values("usuario_id")
            .annotate(total=Sum("xp"))
            .values_list("usuario_id", "total")
        )
        perfis = list(
            PerfilAluno.objects.filter(
                participar_ranking=True, usuario__papel="aluno"
            ).values_list("usuario_id", "serie", "apelido_ranking")
        )
        snapshots = []
        categorias = (
            ("fundamental", lambda serie: serie.startswith("F")),
            ("medio", lambda serie: serie.startswith("M")),
            ("global", lambda serie: True),
        )
        for categoria, pertence in categorias:
            participantes = sorted(
                (
                    (usuario_id, apelido, pontos.get(usuario_id, 0))
                    for usuario_id, serie, apelido in perfis
                    if pertence(serie)
                ),
                key=lambda item: (-item[2], item[1].casefold()),
            )
            posicao_anterior = 0
            xp_anterior = None
            for indice, (_usuario_id, apelido, xp) in enumerate(participantes, start=1):
                if xp != xp_anterior:
                    posicao_anterior = indice
                    xp_anterior = xp
                snapshots.append(
                    ResultadoRanking(
                        periodo=periodo,
                        categoria=categoria,
                        posicao=posicao_anterior,
                        apelido=apelido,
                        xp=xp,
                    )
                )

        ResultadoRanking.objects.bulk_create(snapshots)
        periodo.fechado = True
        periodo.save(update_fields=("fechado",))
        return snapshots


def progresso_patente(xp_vitalicio):
    """Retorna a patente atual e a próxima com base no XP vitalício."""
    patentes = list(Patente.objects.filter(ativa=True).order_by("xp_minimo"))
    if not patentes:
        return None

    atual = None
    proxima = None
    for patente in patentes:
        if patente.xp_minimo <= xp_vitalicio:
            atual = patente
        else:
            proxima = patente
            break

    if proxima is None:
        return {
            "atual": atual,
            "proxima": None,
            "xp_restante": 0,
            "percentual": 100,
        }

    if atual is None:
        inicio = 0
        percentual = 0
    else:
        inicio = atual.xp_minimo
        intervalo = proxima.xp_minimo - inicio
        percentual = min(100, round((xp_vitalicio - inicio) * 100 / intervalo))

    return {
        "atual": atual,
        "proxima": proxima,
        "xp_restante": max(0, proxima.xp_minimo - xp_vitalicio),
        "percentual": percentual,
    }


def _metricas_conquistas(usuario):
    return {
        Conquista.Criterio.QUIZZES_CONCLUIDOS: QuizTentativa.objects.filter(
            usuario=usuario
        ).count(),
        Conquista.Criterio.QUIZZES_PERFEITOS: QuizTentativa.objects.filter(
            usuario=usuario, acertos=F("total_questoes")
        ).count(),
        Conquista.Criterio.XP_VITALICIO: XPTransacao.objects.filter(
            usuario=usuario, validada=True
        ).aggregate(total=Sum("xp"))["total"] or 0,
    }


def atualizar_conquistas(usuario):
    """Registra as conquistas ativas cujo critério o aluno já alcançou."""
    if usuario.papel != "aluno":
        return
    metricas = _metricas_conquistas(usuario)
    for conquista in Conquista.objects.filter(ativa=True):
        if metricas[conquista.criterio] >= conquista.meta:
            ConquistaConcedida.objects.get_or_create(
                usuario=usuario, conquista=conquista
            )


def resumo_conquistas(usuario):
    """Atualiza e retorna conquistas ativas com o progresso do aluno."""
    if usuario.papel != "aluno":
        return []
    metricas = _metricas_conquistas(usuario)
    concedidas = set(
        ConquistaConcedida.objects.filter(usuario=usuario).values_list(
            "conquista_id", flat=True
        )
    )
    itens = []
    for conquista in Conquista.objects.filter(ativa=True):
        atual = metricas[conquista.criterio]
        conquistada = conquista.pk in concedidas
        if not conquistada and atual >= conquista.meta:
            ConquistaConcedida.objects.get_or_create(
                usuario=usuario, conquista=conquista
            )
            conquistada = True
        itens.append(
            {
                "conquista": conquista,
                "progresso": min(atual, conquista.meta),
                "percentual": min(100, round(atual * 100 / conquista.meta)),
                "conquistada": conquistada,
            }
        )
    return itens


def _progresso_missao(usuario, missao):
    tentativas = QuizTentativa.objects.filter(usuario=usuario)
    if missao.inicio:
        tentativas = tentativas.filter(finalizada_em__gte=missao.inicio)
    if missao.fim:
        tentativas = tentativas.filter(finalizada_em__lte=missao.fim)
    if missao.criterio == Missao.Criterio.QUIZZES_PERFEITOS:
        tentativas = tentativas.filter(acertos=F("total_questoes"))
    return tentativas.count()


def conceder_xp_missao(usuario, missao, dia=None):
    """Registra a recompensa configurada para uma missão uma única vez."""
    if usuario.papel != "aluno" or missao.recompensa_xp <= 0:
        return None
    referencia = str(missao.pk)
    existente = XPTransacao.objects.filter(
        usuario=usuario, origem="missao", referencia=referencia
    ).first()
    if existente:
        return existente
    temporada, periodo_anual = _periodos_do_dia(dia)
    if temporada.fechado or periodo_anual.fechado:
        return None
    try:
        with transaction.atomic():
            return XPTransacao.objects.create(
                usuario=usuario,
                regra=None,
                missao=missao,
                origem="missao",
                referencia=referencia,
                atividade=missao.nome[:160],
                xp=missao.recompensa_xp,
                temporada=temporada,
                periodo_anual=periodo_anual,
                validada=True,
            )
    except IntegrityError:
        return XPTransacao.objects.get(
            usuario=usuario, origem="missao", referencia=referencia
        )


def processar_missoes(usuario, agora=None):
    """Atualiza as missões no prazo e registra conclusão e XP atomicamente."""
    if usuario.papel != "aluno":
        return
    agora = agora or timezone.now()
    missoes = Missao.objects.filter(ativa=True).filter(
        Q(inicio__isnull=True) | Q(inicio__lte=agora),
        Q(fim__isnull=True) | Q(fim__gte=agora),
    )
    for missao in missoes:
        with transaction.atomic():
            participacao, _ = MissaoAluno.objects.get_or_create(
                usuario=usuario, missao=missao
            )
            if participacao.concluida_em:
                continue
            atual = _progresso_missao(usuario, missao)
            participacao.progresso = min(atual, missao.meta)
            if atual >= missao.meta:
                if missao.recompensa_xp and not conceder_xp_missao(
                    usuario, missao, timezone.localtime(agora).date()
                ):
                    participacao.save(update_fields=("progresso",))
                    continue
                participacao.concluida_em = agora
            participacao.save(update_fields=("progresso", "concluida_em"))


def resumo_missoes(usuario, agora=None):
    """Retorna missões abertas e o histórico pessoal de participação."""
    if usuario.papel != "aluno":
        return []
    agora = agora or timezone.now()
    processar_missoes(usuario, agora)
    participacoes = {
        item.missao_id: item
        for item in MissaoAluno.objects.filter(usuario=usuario).select_related(
            "missao"
        )
    }
    missoes = Missao.objects.filter(
        Q(ativa=True) | Q(participacoes__usuario=usuario)
    ).distinct()
    itens = []
    for missao in missoes:
        participacao = participacoes.get(missao.pk)
        concluida = bool(participacao and participacao.concluida_em)
        if missao.secreta and not concluida:
            continue
        progresso = participacao.progresso if participacao else 0
        if concluida:
            status = "concluida"
        elif missao.fim and missao.fim < agora:
            status = "encerrada"
        elif missao.inicio and missao.inicio > agora:
            status = "em_breve"
        elif progresso:
            status = "em_andamento"
        else:
            status = "disponivel"
        itens.append(
            {
                "missao": missao,
                "progresso": progresso,
                "percentual": min(100, round(progresso * 100 / missao.meta)),
                "concluida": concluida,
                "status": status,
            }
        )
    return itens
