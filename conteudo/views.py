import hashlib
import calendar
import re
import unicodedata
import uuid
from datetime import date

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.db import IntegrityError, transaction
from django.db.models import (
    Avg,
    Case,
    Count,
    ExpressionWrapper,
    F,
    FloatField,
    IntegerField,
    Max,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Value,
    When,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .decorators import professor_required
from contas.models import PerfilAluno, Usuario

from .forms import (
    AssuntoForm,
    BloqueioColagemAdminForm,
    BloqueioColagemProfessorForm,
    ComentarioMaterialForm,
    DesafioPvPForm,
    EventoCalendarioForm,
    MarcacaoForm,
    MateriaForm,
    NotaAvaliacaoForm,
    PerguntaAlunoForm,
    QuizForm,
    QuizQuestaoFormSet,
    RespostaPerguntaForm,
)
from .models import (
    Assunto,
    ComentarioMaterial,
    ConfiguracaoColagem,
    DesafioPartida,
    DesafioPvP,
    EventoCalendario,
    Marcacao,
    NotificacaoAluno,
    NotaAvaliacao,
    Materia,
    PerguntaAluno,
    Quiz,
    QuizQuestao,
    QuizResposta,
    QuizTentativa,
    RespostaPergunta,
    XPRegra,
    XPTransacao,
)
from .services import (
    atualizar_conquistas,
    conceder_xp,
    notificar_novidade_alunos,
    resumo_conquistas,
    resumo_missoes,
    processar_missoes,
)
from .arena import (
    aceitar_desafio_pvp,
    atualizar_expiracao_desafio,
    criar_desafio_pvp,
    registrar_partida_pvp,
)


def _normalizar_trecho(texto):
    return " ".join(unicodedata.normalize("NFC", texto).split())


def _secoes_leitor(assunto):
    secoes = []
    ocorrencias = {}
    for texto in re.split(r"\n\s*\n", assunto.conteudo_completo.strip()):
        texto = texto.strip()
        if not texto:
            continue
        normalizado = _normalizar_trecho(texto)
        base_id = hashlib.sha256(normalizado.encode("utf-8")).hexdigest()[:24]
        ocorrencias[base_id] = ocorrencias.get(base_id, 0) + 1
        identificador = f"{base_id}-{ocorrencias[base_id]}"
        secoes.append({"id": identificador, "texto": texto})
    return secoes


def _disponivel_agora():
    return Q(publicar_em__isnull=True) | Q(publicar_em__lte=timezone.now())


def _notificar_publicacao_imediata(objeto, tipo, titulo, mensagem, destino, serie):
    agora = timezone.now()
    if not objeto.publicado or (objeto.publicar_em and objeto.publicar_em > agora):
        return
    notificar_novidade_alunos(
        tipo=tipo,
        titulo=titulo,
        mensagem=mensagem,
        destino=destino,
        serie=serie,
    )
    objeto.notificacao_enviada_em = agora
    objeto.save(update_fields=("notificacao_enviada_em",))


@login_required
def calendario(request):
    hoje = timezone.localdate()
    try:
        ano = int(request.GET.get("ano", hoje.year))
        mes = int(request.GET.get("mes", hoje.month))
        primeiro_dia = date(ano, mes, 1)
        if not 2000 <= ano <= 2100:
            raise ValueError
    except (TypeError, ValueError):
        primeiro_dia = hoje.replace(day=1)
        ano, mes = primeiro_dia.year, primeiro_dia.month

    if request.user.papel == Usuario.Papel.ALUNO:
        perfil = _perfil_do_aluno(request)
        eventos = EventoCalendario.objects.filter(serie=perfil.serie)
    elif request.user.papel == Usuario.Papel.PROFESSOR:
        eventos = EventoCalendario.objects.filter(criado_por=request.user)
    else:
        eventos = EventoCalendario.objects.all()
    eventos = list(
        eventos.filter(data__year=ano, data__month=mes).select_related("materia", "criado_por")
    )
    por_data = {}
    for evento in eventos:
        por_data.setdefault(evento.data, []).append(evento)
    semanas = [
        [
            {"data": dia, "fora_do_mes": dia.month != mes, "eventos": por_data.get(dia, [])}
            for dia in semana
        ]
        for semana in calendar.Calendar(firstweekday=0).monthdatescalendar(ano, mes)
    ]
    mes_anterior = date(ano - 1, 12, 1) if mes == 1 else date(ano, mes - 1, 1)
    proximo_mes = date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)
    meses = (
        "janeiro", "fevereiro", "março", "abril", "maio", "junho",
        "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
    )
    return render(
        request,
        "conteudo/calendario.html",
        {
            "semanas": semanas,
            "mes_nome": meses[mes - 1],
            "ano": ano,
            "mes": mes,
            "mes_anterior": mes_anterior,
            "proximo_mes": proximo_mes,
            "hoje": hoje,
            "eventos_mes": eventos,
            "pode_gerenciar": request.user.papel == Usuario.Papel.PROFESSOR,
        },
    )


@professor_required
def evento_calendario_form(request, evento_id=None):
    evento = get_object_or_404(EventoCalendario, pk=evento_id, criado_por=request.user) if evento_id else None
    if request.method == "POST":
        form = EventoCalendarioForm(request.POST, instance=evento)
        if form.is_valid():
            registro = form.save(commit=False)
            registro.criado_por = request.user
            registro.save()
            return redirect("calendario")
    else:
        form = EventoCalendarioForm(instance=evento)
    return render(
        request,
        "conteudo/evento_calendario_form.html",
        {"form": form, "evento": evento},
    )


@professor_required
@require_POST
def excluir_evento_calendario(request, evento_id):
    evento = get_object_or_404(EventoCalendario, pk=evento_id, criado_por=request.user)
    evento.delete()
    return redirect("calendario")


@login_required
@require_GET
def lista_notificacoes(request):
    _exigir_aluno(request)
    notificacoes = NotificacaoAluno.objects.filter(usuario=request.user)[:100]
    return render(
        request,
        "conteudo/notificacoes.html",
        {"notificacoes": notificacoes},
    )


@login_required
@require_GET
def abrir_notificacao(request, notificacao_id):
    _exigir_aluno(request)
    notificacao = get_object_or_404(
        NotificacaoAluno, pk=notificacao_id, usuario=request.user
    )
    if notificacao.lida_em is None:
        notificacao.lida_em = timezone.now()
        notificacao.save(update_fields=("lida_em",))
    if notificacao.destino.startswith("/") and not notificacao.destino.startswith("//"):
        return redirect(notificacao.destino)
    return redirect("notificacoes")


@login_required
def lista_materias(request):
    materias = Materia.objects.filter(destaque=True)
    return render(request, "conteudo/materias.html", {"materias": materias})


@login_required
def detalhe_materia(request, materia_id):
    materia = get_object_or_404(Materia, pk=materia_id)
    series_validas = [codigo for codigo, _ in PerfilAluno.Serie.choices]
    perfil = getattr(request.user, "perfil_aluno", None)
    serie = request.GET.get("serie") or (perfil.serie if perfil else series_validas[0])
    if serie not in series_validas:
        serie = series_validas[0]
    assuntos = materia.assuntos.filter(serie=serie, publicado=True).filter(_disponivel_agora())
    termo = request.GET.get("q", "").strip()
    tipo_material = request.GET.get("tipo", "").strip()
    if termo:
        assuntos = assuntos.filter(
            Q(titulo__icontains=termo)
            | Q(resumo__icontains=termo)
            | Q(objetivos_aprendizagem__icontains=termo)
            | Q(palavras_chave__icontains=termo)
        )
    tipos_materiais = Assunto.TipoMaterial.choices
    if tipo_material in Assunto.TipoMaterial.values:
        assuntos = assuntos.filter(tipo_material=tipo_material)
    else:
        tipo_material = ""
    return render(
        request,
        "conteudo/materia.html",
        {
            "materia": materia,
            "series": PerfilAluno.Serie.choices,
            "serie_atual": serie,
            "assuntos": assuntos,
            "termo": termo,
            "tipo_material_atual": tipo_material,
            "tipos_materiais": tipos_materiais,
        },
    )


@login_required
def leitor(request, assunto_id):
    assunto = get_object_or_404(
        Assunto.objects.select_related("materia").filter(_disponivel_agora()),
        pk=assunto_id,
        publicado=True,
    )
    return _render_leitor(request, assunto)


def _render_leitor(request, assunto, form_comentario=None, status=200):
    secoes = _secoes_leitor(assunto)
    marcacoes = Marcacao.objects.filter(
        usuario=request.user, assunto=assunto
    ).select_related("usuario")
    respostas = ComentarioMaterial.objects.select_related("autor").order_by("criado_em")
    comentarios = (
        ComentarioMaterial.objects.filter(assunto=assunto, resposta_a__isnull=True)
        .select_related("autor")
        .prefetch_related(Prefetch("respostas", queryset=respostas))
    )
    return render(
        request,
        "conteudo/leitor.html",
        {
            "assunto": assunto,
            "secoes": secoes,
            "marcacoes": marcacoes,
            "form": MarcacaoForm(),
            "comentarios": comentarios,
            "form_comentario": form_comentario or ComentarioMaterialForm(),
        },
        status=status,
    )


@login_required
@require_POST
def comentario_material_novo(request, assunto_id, comentario_id=None):
    assunto = get_object_or_404(
        Assunto.objects.filter(_disponivel_agora()), pk=assunto_id, publicado=True
    )
    resposta_a = None
    if comentario_id is not None:
        resposta_a = get_object_or_404(
            ComentarioMaterial,
            pk=comentario_id,
            assunto=assunto,
            resposta_a__isnull=True,
        )
    form = ComentarioMaterialForm(request.POST)
    if form.is_valid():
        comentario = form.save(commit=False)
        comentario.assunto = assunto
        comentario.autor = request.user
        comentario.resposta_a = resposta_a
        comentario.save()
        return redirect(f"{reverse('leitor', args=[assunto.pk])}#comentario-{comentario.pk}")
    return _render_leitor(request, assunto, form_comentario=form, status=400)


@login_required
def baixar_material(request, assunto_id):
    assunto = get_object_or_404(
        Assunto.objects.only("id", "titulo", "arquivo").filter(_disponivel_agora()),
        pk=assunto_id,
        publicado=True,
    )
    if not assunto.arquivo:
        raise Http404
    try:
        resposta = FileResponse(
            assunto.arquivo.open("rb"),
            as_attachment=True,
            filename=f"{slugify(assunto.titulo) or 'material'}.pdf",
            content_type="application/pdf",
        )
    except OSError as exc:
        raise Http404 from exc
    resposta["Cache-Control"] = "private, no-store"
    resposta["X-Content-Type-Options"] = "nosniff"
    resposta["Referrer-Policy"] = "no-referrer"
    return resposta


@login_required
def salvar_marcacao(request, assunto_id, marcacao_id=None):
    if request.method != "POST" and marcacao_id is None:
        return redirect("leitor", assunto_id=assunto_id)
    assunto = get_object_or_404(
        Assunto.objects.filter(_disponivel_agora()), pk=assunto_id, publicado=True
    )
    instance = None
    if marcacao_id:
        instance = get_object_or_404(
            Marcacao,
            pk=marcacao_id,
            assunto=assunto,
            usuario=request.user,
        )
    form = MarcacaoForm(
        request.POST if request.method == "POST" else None, instance=instance
    )
    secoes = _secoes_leitor(assunto)
    if request.method == "POST" and form.is_valid():
        trecho_id = form.cleaned_data["trecho_id"]
        trecho_texto = form.cleaned_data["trecho_texto"]
        secao = next((s for s in secoes if s["id"] == trecho_id), None)
        if not secao or _normalizar_trecho(trecho_texto) not in _normalizar_trecho(
            secao["texto"]
        ):
            form.add_error("trecho_texto", "Selecione um trecho deste conteúdo.")
        else:
            marcacao = form.save(commit=False)
            marcacao.usuario = request.user
            marcacao.assunto = assunto
            marcacao.save()
            return redirect(
                f"{reverse('leitor', args=[assunto.pk])}#marcacao-{marcacao.pk}"
            )
    marcacoes = Marcacao.objects.filter(usuario=request.user, assunto=assunto)
    return render(
        request,
        "conteudo/leitor.html",
        {
            "assunto": assunto,
            "secoes": secoes,
            "marcacoes": marcacoes,
            "form": form,
            "marcacao_editando": instance,
        },
        status=400 if request.method == "POST" else 200,
    )


@login_required
def excluir_marcacao(request, assunto_id, marcacao_id):
    if request.method != "POST":
        return redirect("leitor", assunto_id=assunto_id)
    marcacao = get_object_or_404(
        Marcacao,
        pk=marcacao_id,
        assunto_id=assunto_id,
        usuario=request.user,
    )
    marcacao.delete()
    return redirect("leitor", assunto_id=assunto_id)


@login_required
def minhas_marcacoes(request):
    marcacoes = Marcacao.objects.filter(usuario=request.user).select_related(
        "assunto", "assunto__materia"
    )
    return render(
        request, "conteudo/minhas_marcacoes.html", {"marcacoes": marcacoes}
    )


def _exigir_aluno(request):
    if request.user.papel != "aluno":
        raise PermissionDenied


def _perfil_do_aluno(request):
    _exigir_aluno(request)
    perfil = getattr(request.user, "perfil_aluno", None)
    if perfil is None:
        raise PermissionDenied
    return perfil


def _bloqueio_colagem_ativo():
    configuracao = ConfiguracaoColagem.objects.filter(pk=1).first()
    return configuracao.bloqueio_ativo if configuracao else False


@professor_required
def configuracao_colagem_professor(request):
    configuracao, _ = ConfiguracaoColagem.objects.get_or_create(pk=1)
    if request.method == "POST":
        form = BloqueioColagemProfessorForm(request.POST, instance=configuracao)
        if form.is_valid():
            form.save()
            return redirect("configuracao_colagem_professor")
    else:
        form = BloqueioColagemProfessorForm(instance=configuracao)
    return render(
        request,
        "conteudo/configuracao_colagem.html",
        {
            "form": form,
            "bloqueio_ativo": configuracao.bloqueio_ativo,
            "bloqueio_professor_ativo": configuracao.bloquear_colagem_professor,
            "bloqueio_admin_ativo": configuracao.bloquear_colagem_admin,
            "origem_configuracao": "professor",
        },
    )


@login_required
def configuracao_colagem_admin(request):
    if request.user.papel != Usuario.Papel.ADMIN and not request.user.is_superuser:
        raise PermissionDenied
    configuracao, _ = ConfiguracaoColagem.objects.get_or_create(pk=1)
    if request.method == "POST":
        form = BloqueioColagemAdminForm(request.POST, instance=configuracao)
        if form.is_valid():
            form.save()
            return redirect("configuracao_colagem_admin")
    else:
        form = BloqueioColagemAdminForm(instance=configuracao)
    return render(
        request,
        "conteudo/configuracao_colagem.html",
        {
            "form": form,
            "bloqueio_ativo": configuracao.bloqueio_ativo,
            "bloqueio_professor_ativo": configuracao.bloquear_colagem_professor,
            "bloqueio_admin_ativo": configuracao.bloquear_colagem_admin,
            "origem_configuracao": "administrador",
        },
    )


@login_required
def lista_perguntas(request):
    perfil = _perfil_do_aluno(request)
    if request.method == "POST":
        form = PerguntaAlunoForm(request.POST)
        if form.is_valid():
            pergunta = form.save(commit=False)
            pergunta.autor = request.user
            pergunta.serie = perfil.serie
            pergunta.save()
            return redirect("perguntas")
    else:
        form = PerguntaAlunoForm()

    perguntas = (
        PerguntaAluno.objects.filter(serie=perfil.serie)
        .filter(Q(status=PerguntaAluno.Status.APROVADA) | Q(autor=request.user))
        .select_related("materia")
        .annotate(
            respostas_publicadas=Count(
                "respostas",
                filter=Q(respostas__status=RespostaPergunta.Status.APROVADA),
                distinct=True,
            )
        )
    )
    return render(
        request,
        "conteudo/perguntas.html",
        {
            "form": form,
            "perguntas": perguntas,
            "bloquear_colagem": _bloqueio_colagem_ativo(),
        },
    )


@login_required
def detalhe_pergunta(request, pergunta_id):
    perfil = _perfil_do_aluno(request)
    pergunta = get_object_or_404(
        PerguntaAluno.objects.select_related("materia"),
        pk=pergunta_id,
        serie=perfil.serie,
    )
    if pergunta.status != PerguntaAluno.Status.APROVADA and pergunta.autor_id != request.user.pk:
        raise PermissionDenied

    if request.method == "POST":
        form = RespostaPerguntaForm(request.POST)
        valido = form.is_valid()
        if pergunta.autor_id == request.user.pk:
            form.add_error(None, "Você não pode responder à própria pergunta.")
        elif valido:
            resposta = form.save(commit=False)
            resposta.pergunta = pergunta
            resposta.autor = request.user
            resposta.save()
            return redirect("pergunta_detalhe", pergunta_id=pergunta.pk)
    else:
        form = RespostaPerguntaForm()

    respostas = pergunta.respostas.filter(
        Q(status=RespostaPergunta.Status.APROVADA) | Q(autor=request.user)
    )
    return render(
        request,
        "conteudo/pergunta_detalhe.html",
        {
            "pergunta": pergunta,
            "respostas": respostas,
            "form": form,
            "bloquear_colagem": _bloqueio_colagem_ativo(),
        },
        status=400 if request.method == "POST" else 200,
    )


def _moderar_publicacao(request, objeto, status_pendente, model):
    acao = request.POST.get("acao")
    status = {
        "aprovar": model.Status.APROVADA,
        "rejeitar": model.Status.REJEITADA,
    }.get(acao)
    if status is None:
        raise PermissionDenied
    atualizados = model.objects.filter(
        pk=objeto.pk, status=status_pendente
    ).update(status=status, moderada_por=request.user, moderada_em=timezone.now())
    if not atualizados:
        raise PermissionDenied


@professor_required
@require_POST
def moderar_pergunta(request, pergunta_id):
    pergunta = get_object_or_404(PerguntaAluno, pk=pergunta_id)
    _moderar_publicacao(
        request,
        pergunta,
        PerguntaAluno.Status.PENDENTE,
        PerguntaAluno,
    )
    return redirect("painel_professor")


@professor_required
@require_POST
def moderar_resposta(request, resposta_id):
    resposta = get_object_or_404(RespostaPergunta, pk=resposta_id)
    _moderar_publicacao(
        request,
        resposta,
        RespostaPergunta.Status.PENDENTE,
        RespostaPergunta,
    )
    return redirect("painel_professor")


@login_required
def lista_quizzes(request):
    _exigir_aluno(request)
    perfil = getattr(request.user, "perfil_aluno", None)
    serie = perfil.serie if perfil else ""
    quizzes_disponiveis = (
        Quiz.objects.filter(publicado=True)
        .filter(_disponivel_agora())
        .annotate(
            total_questoes=Count("questoes", distinct=True),
            tentativas_aluno=Count(
                "tentativas",
                filter=Q(tentativas__usuario=request.user),
                distinct=True,
            ),
            melhor_percentual=Subquery(
                QuizTentativa.objects.filter(
                    usuario=request.user, quiz_id=OuterRef("pk")
                )
                .annotate(
                    percentual_calculado=ExpressionWrapper(
                        100.0 * F("acertos") / F("total_questoes"),
                        output_field=FloatField(),
                    )
                )
                .order_by("-percentual_calculado", "-finalizada_em")
                .values("percentual_calculado")[:1]
            ),
        )
        .filter(total_questoes__gt=0)
        .select_related("materia")
        .order_by(
            Case(
                When(serie=serie, then=Value(0)),
                When(serie="", then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            ),
            "materia__nome",
            "titulo",
        )
    )
    materias = Materia.objects.filter(
        quizzes__publicado=True,
        quizzes__questoes__isnull=False,
    ).distinct().order_by("nome")
    materias = materias.filter(
        Q(quizzes__publicar_em__isnull=True) | Q(quizzes__publicar_em__lte=timezone.now())
    ).distinct()
    termo = request.GET.get("q", "").strip()
    materia_id = request.GET.get("materia", "").strip()
    quizzes = quizzes_disponiveis
    if termo:
        quizzes = quizzes.filter(
            Q(titulo__icontains=termo)
            | Q(descricao__icontains=termo)
            | Q(materia__nome__icontains=termo)
        )
    if materia_id.isdecimal() and materias.filter(pk=materia_id).exists():
        quizzes = quizzes.filter(materia_id=materia_id)
    else:
        materia_id = ""
    tentativas = QuizTentativa.objects.filter(usuario=request.user).select_related(
        "quiz", "quiz__materia"
    )[:8]
    return render(
        request,
        "conteudo/quizzes.html",
        {
            "quizzes": quizzes,
            "tentativas": tentativas,
            "materias": materias,
            "termo": termo,
            "materia_atual": materia_id,
            "ha_quizzes_disponiveis": quizzes_disponiveis.exists(),
        },
    )


@login_required
def arena(request):
    _perfil_do_aluno(request)
    if request.method == "POST":
        form = DesafioPvPForm(request.POST, usuario=request.user)
        if form.is_valid():
            try:
                desafio = criar_desafio_pvp(request.user, form.cleaned_data["quiz"])
            except ValueError as exc:
                form.add_error("quiz", str(exc))
            else:
                return redirect("arena_desafio", convite=desafio.convite)
    else:
        form = DesafioPvPForm(usuario=request.user)

    desafios = list(
        DesafioPvP.objects.filter(Q(criador=request.user) | Q(convidado=request.user))
        .select_related("quiz", "quiz__materia")[:30]
    )
    for indice, desafio in enumerate(desafios):
        desafios[indice] = atualizar_expiracao_desafio(desafio.pk)
    return render(
        request,
        "conteudo/arena.html",
        {"form": form, "desafios": desafios},
    )


@login_required
def arena_desafio(request, convite):
    _perfil_do_aluno(request)
    desafio = get_object_or_404(
        DesafioPvP.objects.select_related("quiz", "quiz__materia"), convite=convite
    )
    desafio = atualizar_expiracao_desafio(desafio.pk)
    participante = request.user.pk in {desafio.criador_id, desafio.convidado_id}
    if not participante:
        if (
            desafio.status != DesafioPvP.Status.ABERTO
            or request.user.perfil_aluno.serie != desafio.serie
        ):
            raise Http404

    erro = ""
    status_http = 200
    if request.method == "POST":
        if not participante or desafio.status != DesafioPvP.Status.EM_ANDAMENTO:
            raise PermissionDenied
        respostas = {
            ordem: request.POST.get(f"resposta_{ordem}", "")
            for ordem in range(1, 11)
        }
        try:
            registrar_partida_pvp(desafio.pk, request.user, respostas)
        except ValueError as exc:
            erro = str(exc)
            status_http = 400
        else:
            return redirect("arena_desafio", convite=desafio.convite)

    partida = None
    perguntas = []
    resultado_pessoal = ""
    pontos_proprios = pontos_adversario = None
    if participante:
        partida = DesafioPartida.objects.filter(
            desafio=desafio, usuario=request.user
        ).first()
        if (
            desafio.status == DesafioPvP.Status.EM_ANDAMENTO
            and (partida is None or partida.finalizada_em is None)
        ):
            perguntas = [
                {
                    "ordem": item.ordem,
                    "enunciado": item.enunciado,
                    "alternativas": [
                        ("A", item.alternativa_a),
                        ("B", item.alternativa_b),
                        ("C", item.alternativa_c),
                        ("D", item.alternativa_d),
                    ],
                }
                for item in desafio.questoes.order_by("ordem")
            ]
        if desafio.status == DesafioPvP.Status.CONCLUIDO:
            partidas = {
                item.usuario_id: item.acertos
                for item in desafio.partidas.filter(finalizada_em__isnull=False)
            }
            adversario_id = (
                desafio.convidado_id
                if request.user.pk == desafio.criador_id
                else desafio.criador_id
            )
            pontos_proprios = partidas.get(request.user.pk)
            pontos_adversario = partidas.get(adversario_id)
            if desafio.resultado == DesafioPvP.Resultado.EMPATE:
                resultado_pessoal = "O desafio terminou empatado."
            elif (
                desafio.resultado == DesafioPvP.Resultado.CRIADOR
                and request.user.pk == desafio.criador_id
            ) or (
                desafio.resultado == DesafioPvP.Resultado.CONVIDADO
                and request.user.pk == desafio.convidado_id
            ):
                resultado_pessoal = "Você venceu o desafio!"
            else:
                resultado_pessoal = "Seu adversário venceu desta vez."

    convite_url = request.build_absolute_uri(
        reverse("arena_desafio", args=(desafio.convite,))
    )
    return render(
        request,
        "conteudo/arena_desafio.html",
        {
            "desafio": desafio,
            "participante": participante,
            "criou_desafio": request.user.pk == desafio.criador_id,
            "partida": partida,
            "perguntas": perguntas,
            "resultado_pessoal": resultado_pessoal,
            "pontos_proprios": pontos_proprios,
            "pontos_adversario": pontos_adversario,
            "convite_url": convite_url,
            "erro": erro,
        },
        status=status_http,
    )


@login_required
@require_POST
def arena_aceitar(request, convite):
    _perfil_do_aluno(request)
    desafio = get_object_or_404(DesafioPvP, convite=convite)
    if request.user.perfil_aluno.serie != desafio.serie:
        raise Http404
    try:
        aceitar_desafio_pvp(desafio.pk, request.user)
    except ValueError as exc:
        desafio = atualizar_expiracao_desafio(desafio.pk)
        return render(
            request,
            "conteudo/arena_desafio.html",
            {
                "desafio": desafio,
                "participante": request.user.pk in {desafio.criador_id, desafio.convidado_id},
                "criou_desafio": request.user.pk == desafio.criador_id,
                "partida": None,
                "perguntas": [],
                "erro": str(exc),
                "convite_url": request.build_absolute_uri(
                    reverse("arena_desafio", args=(desafio.convite,))
                ),
            },
            status=400,
        )
    return redirect("arena_desafio", convite=desafio.convite)


@login_required
@require_POST
def arena_cancelar(request, convite):
    _perfil_do_aluno(request)
    with transaction.atomic():
        desafio = get_object_or_404(
            DesafioPvP.objects.select_for_update(), convite=convite
        )
        if desafio.criador_id != request.user.pk or desafio.status != DesafioPvP.Status.ABERTO:
            raise PermissionDenied
        desafio.status = (
            DesafioPvP.Status.EXPIRADO
            if desafio.expira_em <= timezone.now()
            else DesafioPvP.Status.CANCELADO
        )
        desafio.save(update_fields=("status",))
    return redirect("arena_desafio", convite=desafio.convite)


@login_required
def lista_conquistas(request):
    _exigir_aluno(request)
    return render(
        request,
        "conteudo/conquistas.html",
        {"conquistas": resumo_conquistas(request.user)},
    )


@login_required
def lista_missoes(request):
    _exigir_aluno(request)
    return render(
        request,
        "conteudo/missoes.html",
        {"missoes": resumo_missoes(request.user)},
    )


def _contexto_quiz(quiz, questoes, token_envio, erro=""):
    # Só envia os textos das alternativas ao navegador. A chave correta fica
    # fora do contexto até que o servidor registre a tentativa.
    itens = []
    for questao in questoes:
        itens.append(
            {
                "id": questao.pk,
                "enunciado": questao.enunciado,
                "alternativas": [
                    ("A", questao.alternativa_a),
                    ("B", questao.alternativa_b),
                    ("C", questao.alternativa_c),
                    ("D", questao.alternativa_d),
                ],
            }
        )
    return {
        "quiz": quiz,
        "questoes": itens,
        "token_envio": token_envio,
        "erro": erro,
    }


@login_required
def responder_quiz(request, quiz_id):
    _exigir_aluno(request)
    quiz = get_object_or_404(
        Quiz.objects.select_related("materia").filter(_disponivel_agora()),
        pk=quiz_id,
        publicado=True,
    )
    questoes = list(quiz.questoes.all())
    if not questoes:
        return redirect("quizzes")

    if request.method == "GET":
        return render(
            request,
            "conteudo/responder_quiz.html",
            _contexto_quiz(quiz, questoes, uuid.uuid4()),
        )

    try:
        token_envio = uuid.UUID(request.POST.get("token_envio", ""))
    except (ValueError, TypeError, AttributeError):
        token_envio = None
    if token_envio is None:
        return render(
            request,
            "conteudo/responder_quiz.html",
            _contexto_quiz(
                quiz, questoes, uuid.uuid4(), "O formulário expirou. Revise e envie novamente."
            ),
            status=400,
        )

    tentativa_existente = QuizTentativa.objects.filter(
        usuario=request.user, quiz=quiz, token_envio=token_envio
    ).first()
    if tentativa_existente:
        return redirect("resultado_quiz", tentativa_id=tentativa_existente.pk)

    respostas = {}
    erro = ""
    for questao in questoes:
        escolha = request.POST.get(f"resposta_{questao.pk}", "")
        if escolha not in QuizQuestao.AlternativaCorreta.values:
            erro = "Responda todas as questões antes de enviar."
            break
        respostas[questao.pk] = escolha
        if sum(
            bool(valor)
            for valor in (
                questao.resposta_correta == alternativa
                for alternativa in QuizQuestao.AlternativaCorreta.values
            )
        ) != 1:
            erro = "Este quiz está com uma questão configurada incorretamente. Avise a equipe."
            break

    if erro:
        return render(
            request,
            "conteudo/responder_quiz.html",
            _contexto_quiz(quiz, questoes, token_envio, erro),
            status=400,
        )

    acertos = sum(
        escolha == questao.resposta_correta for questao in questoes
    )
    try:
        with transaction.atomic():
            tentativa = QuizTentativa.objects.create(
                usuario=request.user,
                quiz=quiz,
                token_envio=token_envio,
                total_questoes=len(questoes),
                acertos=acertos,
            )
            QuizResposta.objects.bulk_create(
                [
                    QuizResposta(
                        tentativa=tentativa,
                        questao=questao,
                        alternativa_escolhida=respostas[questao.pk],
                        acertou=respostas[questao.pk] == questao.resposta_correta,
                    )
                    for questao in questoes
                ]
            )
            conceder_xp(
                request.user,
                XPRegra.Atividade.QUIZ,
                tentativa.pk,
                quiz.titulo,
            )
            atualizar_conquistas(request.user)
            processar_missoes(request.user)
    except IntegrityError:
        tentativa = get_object_or_404(
            QuizTentativa,
            usuario=request.user,
            quiz=quiz,
            token_envio=token_envio,
        )
    return redirect("resultado_quiz", tentativa_id=tentativa.pk)


@login_required
def resultado_quiz(request, tentativa_id):
    _exigir_aluno(request)
    tentativa = get_object_or_404(
        QuizTentativa.objects.select_related("quiz", "quiz__materia"),
        pk=tentativa_id,
        usuario=request.user,
    )
    respostas = tentativa.respostas.select_related("questao")
    resultado = []
    for resposta in respostas:
        questao = resposta.questao
        resultado.append(
            {
                "questao": questao,
                "escolhida": resposta.alternativa_escolhida,
                "acertou": resposta.acertou,
                "correta": questao.resposta_correta,
                "alternativas": [
                    ("A", questao.alternativa_a),
                    ("B", questao.alternativa_b),
                    ("C", questao.alternativa_c),
                    ("D", questao.alternativa_d),
                ],
            }
        )
    xp_recebido = XPTransacao.objects.filter(
        usuario=request.user,
        origem=XPRegra.Atividade.QUIZ,
        referencia=str(tentativa.pk),
    ).first()
    return render(
        request,
        "conteudo/resultado_quiz.html",
        {
            "tentativa": tentativa,
            "resultado": resultado,
            "xp_recebido": xp_recebido,
        },
    )
@professor_required
def painel_professor(request):
    assuntos = Assunto.objects.filter(autor=request.user).select_related("materia")
    perguntas_pendentes = PerguntaAluno.objects.filter(
        status=PerguntaAluno.Status.PENDENTE
    ).select_related("materia", "autor", "autor__perfil_aluno")
    respostas_pendentes = RespostaPergunta.objects.filter(
        status=RespostaPergunta.Status.PENDENTE
    ).select_related(
        "autor", "autor__perfil_aluno", "pergunta", "pergunta__materia"
    )


    quizzes = (
        Quiz.objects.filter(criado_por=request.user)
        .select_related("materia")
        .annotate(
            total_questoes=Count("questoes", distinct=True),
            total_tentativas=Count("tentativas", distinct=True),
        )
    )
    return render(
        request,
        "conteudo/painel_professor.html",
        {
            "assuntos": assuntos,
            "quizzes": quizzes,
            "perguntas_pendentes": perguntas_pendentes,
            "respostas_pendentes": respostas_pendentes,
            "agora": timezone.now(),
        },
    )


@professor_required
def materia_nova(request):
    if request.method == "POST":
        form = MateriaForm(request.POST)
        if form.is_valid():
            materia = form.save()
            notificar_novidade_alunos(
                tipo=NotificacaoAluno.Tipo.MATERIA,
                titulo=f"Nova matéria: {materia.nome}",
                mensagem="Uma nova matéria foi adicionada ao StudyVerse.",
                destino=reverse("materias"),
            )
            return redirect("painel_professor")
    else:
        form = MateriaForm()
    return render(request, "conteudo/materia_form.html", {"form": form})


@professor_required
def caderneta_professor(request):
    quizzes = Quiz.objects.filter(criado_por=request.user).select_related("materia")
    quiz_id = request.GET.get("quiz", "").strip()
    serie = request.GET.get("serie", "").strip()
    quiz_atual = quizzes.filter(pk=quiz_id).first() if quiz_id.isdecimal() else None
    series_validas = {codigo for codigo, _ in PerfilAluno.Serie.choices}
    if serie not in series_validas:
        serie = ""

    escopo = Q(tentativas_quiz__quiz__criado_por=request.user)
    if quiz_atual:
        escopo &= Q(tentativas_quiz__quiz=quiz_atual)
    else:
        quiz_id = ""
    if serie:
        escopo &= Q(tentativas_quiz__usuario__perfil_aluno__serie=serie)

    percentual = ExpressionWrapper(
        100.0 * F("tentativas_quiz__acertos") / F("tentativas_quiz__total_questoes"),
        output_field=FloatField(),
    )
    alunos = (
        Usuario.objects.filter(papel=Usuario.Papel.ALUNO)
        .filter(escopo)
        .annotate(
            total_tentativas=Count("tentativas_quiz", filter=escopo, distinct=True),
            quizzes_concluidos=Count(
                "tentativas_quiz__quiz", filter=escopo, distinct=True
            ),
            media_percentual=Avg(percentual, filter=escopo),
            ultima_atividade=Max("tentativas_quiz__finalizada_em", filter=escopo),
        )
        .select_related("perfil_aluno")
        .order_by("perfil_aluno__serie", "username")
    )
    tentativas_recentes = (
        QuizTentativa.objects.filter(quiz__criado_por=request.user)
        .filter(quiz=quiz_atual) if quiz_atual else
        QuizTentativa.objects.filter(quiz__criado_por=request.user)
    )
    if serie:
        tentativas_recentes = tentativas_recentes.filter(
            usuario__perfil_aluno__serie=serie
        )
    tentativas_recentes = tentativas_recentes.select_related(
        "usuario", "usuario__perfil_aluno", "quiz", "quiz__materia"
    )[:20]
    notas = NotaAvaliacao.objects.filter(professor=request.user).select_related(
        "aluno", "aluno__perfil_aluno", "materia"
    )
    if serie:
        notas = notas.filter(aluno__perfil_aluno__serie=serie)
    return render(
        request,
        "conteudo/caderneta_professor.html",
        {
            "alunos": alunos,
            "quizzes": quizzes,
            "quiz_atual": quiz_atual,
            "quiz_id": quiz_id,
            "series": PerfilAluno.Serie.choices,
            "serie_atual": serie,
            "tentativas_recentes": tentativas_recentes,
            "notas_avaliacao": notas[:50],
        },
    )


@professor_required
def nota_avaliacao_form(request, nota_id=None):
    nota = None
    if nota_id is not None:
        nota = get_object_or_404(NotaAvaliacao, pk=nota_id, professor=request.user)
    if request.method == "POST":
        form = NotaAvaliacaoForm(request.POST, instance=nota, professor=request.user)
        if form.is_valid():
            registro = form.save(commit=False)
            registro.professor = request.user
            registro.save()
            return redirect("caderneta_professor")
    else:
        form = NotaAvaliacaoForm(instance=nota, professor=request.user)
    return render(
        request,
        "conteudo/nota_avaliacao_form.html",
        {"form": form, "nota": nota},
    )


@professor_required
@require_POST
def excluir_nota_avaliacao(request, nota_id):
    nota = get_object_or_404(NotaAvaliacao, pk=nota_id, professor=request.user)
    nota.delete()
    return redirect("caderneta_professor")


@login_required
def minhas_notas(request):
    perfil = _perfil_do_aluno(request)
    notas = NotaAvaliacao.objects.filter(aluno=request.user).select_related(
        "professor", "materia"
    )
    return render(
        request,
        "conteudo/minhas_notas.html",
        {"notas": notas, "serie": perfil.get_serie_display()},
    )
def quiz_form(request, quiz_id=None):
    quiz = None
    if quiz_id is not None:
        quiz = get_object_or_404(
            Quiz, pk=quiz_id, criado_por=request.user
        )
        if quiz.tentativas.exists():
            return render(
                request,
                "conteudo/quiz_bloqueado.html",
                {"quiz": quiz},
                status=403,
            )
    publicado_antes = bool(quiz and quiz.publicado)

    if request.method == "POST":
        form = QuizForm(request.POST, instance=quiz)
        formset = QuizQuestaoFormSet(request.POST, instance=quiz)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                quiz = form.save(commit=False)
                if quiz.pk is None:
                    quiz.criado_por = request.user
                if quiz.publicado and not publicado_antes:
                    quiz.notificacao_enviada_em = None
                quiz.save()
                formset.instance = quiz
                formset.save()
            if quiz.publicado and not publicado_antes:
                _notificar_publicacao_imediata(
                    quiz,
                    NotificacaoAluno.Tipo.QUIZ,
                    f"Novo quiz: {quiz.titulo}",
                    f"{quiz.materia.nome} - {quiz.get_serie_display() if quiz.serie else 'Todas as s\u00e9ries'}",
                    reverse("responder_quiz", args=[quiz.pk]),
                    quiz.serie,
                )
            return redirect("painel_professor")
    else:
        form = QuizForm(instance=quiz)
        formset = QuizQuestaoFormSet(instance=quiz)
    return render(
        request,
        "conteudo/quiz_form.html",
        {"form": form, "formset": formset, "quiz": quiz},
    )


@professor_required
def quiz_novo(request):
    return quiz_form(request)


@professor_required
def quiz_editar(request, quiz_id):
    return quiz_form(request, quiz_id=quiz_id)


@professor_required
@require_POST
def quiz_duplicar(request, quiz_id):
    quiz_original = get_object_or_404(
        Quiz.objects.prefetch_related("questoes"),
        pk=quiz_id,
        criado_por=request.user,
    )
    with transaction.atomic():
        copia = Quiz.objects.create(
            materia=quiz_original.materia,
            titulo=f"{quiz_original.titulo[:110]} (cópia)",
            descricao=quiz_original.descricao,
            serie=quiz_original.serie,
            publicado=False,
            criado_por=request.user,
        )
        QuizQuestao.objects.bulk_create(
            [
                QuizQuestao(
                    quiz=copia,
                    enunciado=questao.enunciado,
                    alternativa_a=questao.alternativa_a,
                    alternativa_b=questao.alternativa_b,
                    alternativa_c=questao.alternativa_c,
                    alternativa_d=questao.alternativa_d,
                    resposta_correta=questao.resposta_correta,
                    explicacao=questao.explicacao,
                    ordem=questao.ordem,
                )
                for questao in quiz_original.questoes.all()
            ]
        )
    return redirect("painel_professor")


@professor_required
@require_POST
def quiz_excluir_rascunho(request, quiz_id):
    quiz = get_object_or_404(
        Quiz, pk=quiz_id, criado_por=request.user, publicado=False
    )
    if quiz.tentativas.exists():
        raise PermissionDenied
    quiz.delete()
    return redirect("painel_professor")


@professor_required
def assunto_form(request, assunto_id=None):
    assunto = None
    if assunto_id:
        assunto = get_object_or_404(Assunto, pk=assunto_id, autor=request.user)
    publicado_antes = bool(assunto and assunto.publicado)
    if request.method == "POST":
        form = AssuntoForm(request.POST, request.FILES, instance=assunto)
        if form.is_valid():
            arquivo_anterior = (
                assunto.arquivo.name if assunto and assunto.arquivo else None
            )
            novo = form.save(commit=False)
            novo.autor = request.user
            if novo.publicado and not publicado_antes:
                novo.notificacao_enviada_em = None
            novo.save()
            if novo.publicado and not publicado_antes:
                _notificar_publicacao_imediata(
                    novo,
                    NotificacaoAluno.Tipo.MATERIAL,
                    f"Novo material: {novo.titulo}",
                    f"{novo.materia.nome} - {novo.get_serie_display()}",
                    reverse("leitor", args=[novo.pk]),
                    novo.serie,
                )
            if arquivo_anterior and arquivo_anterior != novo.arquivo.name:
                novo.arquivo.storage.delete(arquivo_anterior)
            return redirect("painel_professor")
    else:
        form = AssuntoForm(instance=assunto)
    return render(
        request, "conteudo/assunto_form.html", {"form": form, "assunto": assunto}
    )
