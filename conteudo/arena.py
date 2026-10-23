from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from contas.models import Usuario

from .models import (
    DesafioPartida,
    DesafioPvP,
    DesafioQuestao,
    DesafioResposta,
    Quiz,
    QuizQuestao,
)

TOTAL_QUESTOES_DESAFIO = 10
PRAZO_CONVITE = timedelta(hours=48)


def criar_desafio_pvp(criador, quiz, agora=None):
    agora = agora or timezone.now()
    perfil = getattr(criador, "perfil_aluno", None)
    if criador.papel != Usuario.Papel.ALUNO or perfil is None:
        raise PermissionDenied

    with transaction.atomic():
        quiz = Quiz.objects.select_for_update().get(pk=quiz.pk)
        if (
            not quiz.publicado
            or (quiz.publicar_em and quiz.publicar_em > agora)
            or (quiz.serie and quiz.serie != perfil.serie)
        ):
            raise ValueError("Esse quiz não está disponível para sua série.")
        questoes = list(quiz.questoes.order_by("ordem", "pk")[:TOTAL_QUESTOES_DESAFIO])
        if len(questoes) != TOTAL_QUESTOES_DESAFIO:
            raise ValueError("O quiz precisa ter pelo menos dez questões.")

        desafio = DesafioPvP.objects.create(
            criador=criador,
            quiz=quiz,
            serie=perfil.serie,
            expira_em=agora + PRAZO_CONVITE,
        )
        DesafioQuestao.objects.bulk_create(
            [
                DesafioQuestao(
                    desafio=desafio,
                    ordem=indice,
                    enunciado=questao.enunciado,
                    alternativa_a=questao.alternativa_a,
                    alternativa_b=questao.alternativa_b,
                    alternativa_c=questao.alternativa_c,
                    alternativa_d=questao.alternativa_d,
                    resposta_correta=questao.resposta_correta,
                )
                for indice, questao in enumerate(questoes, start=1)
            ]
        )
    return desafio


def aceitar_desafio_pvp(desafio_id, convidado, agora=None):
    agora = agora or timezone.now()
    perfil = getattr(convidado, "perfil_aluno", None)
    if convidado.papel != Usuario.Papel.ALUNO or perfil is None:
        raise PermissionDenied

    erro = None
    with transaction.atomic():
        desafio = DesafioPvP.objects.select_for_update().get(pk=desafio_id)
        if desafio.status != DesafioPvP.Status.ABERTO:
            erro = "Este convite não está mais disponível."
        elif desafio.expira_em <= agora:
            desafio.status = DesafioPvP.Status.EXPIRADO
            desafio.save(update_fields=("status",))
            erro = "O convite expirou."
        elif desafio.criador_id == convidado.pk:
            erro = "Você não pode aceitar seu próprio convite."
        elif desafio.serie != perfil.serie:
            erro = "Este desafio é para estudantes da mesma série do criador."
        else:
            desafio.convidado = convidado
            desafio.status = DesafioPvP.Status.EM_ANDAMENTO
            desafio.save(update_fields=("convidado", "status"))

    if erro:
        raise ValueError(erro)
    return desafio


def atualizar_expiracao_desafio(desafio_id, agora=None):
    agora = agora or timezone.now()
    with transaction.atomic():
        desafio = DesafioPvP.objects.select_for_update().get(pk=desafio_id)
        if (
            desafio.status in {DesafioPvP.Status.ABERTO, DesafioPvP.Status.EM_ANDAMENTO}
            and desafio.expira_em <= agora
        ):
            desafio.status = DesafioPvP.Status.EXPIRADO
            desafio.save(update_fields=("status",))
        return desafio


def registrar_partida_pvp(desafio_id, usuario, respostas, agora=None):
    agora = agora or timezone.now()
    erro = None
    partida_salva = None
    with transaction.atomic():
        desafio = DesafioPvP.objects.select_for_update().get(pk=desafio_id)
        if desafio.status != DesafioPvP.Status.EM_ANDAMENTO:
            erro = "Este desafio não está aceitando respostas."
        elif desafio.expira_em <= agora:
            desafio.status = DesafioPvP.Status.EXPIRADO
            desafio.save(update_fields=("status",))
            erro = "O desafio expirou antes de os dois jogadores concluírem."
        elif usuario.pk not in {desafio.criador_id, desafio.convidado_id}:
            raise PermissionDenied

        if erro:
            pass
        else:
            ordens_esperadas = set(range(1, TOTAL_QUESTOES_DESAFIO + 1))
            if set(respostas) != ordens_esperadas or any(
                resposta not in QuizQuestao.AlternativaCorreta.values
                for resposta in respostas.values()
            ):
                erro = "Responda às dez questões antes de enviar."
            else:
                partida, _ = DesafioPartida.objects.get_or_create(
                    desafio=desafio, usuario=usuario
                )
                if partida.finalizada_em:
                    erro = "Sua participação neste desafio já foi enviada."
                else:
                    questoes = list(desafio.questoes.order_by("ordem"))
                    respostas_criadas = []
                    acertos = 0
                    for questao in questoes:
                        escolha = respostas[questao.ordem]
                        acertou = escolha == questao.resposta_correta
                        acertos += int(acertou)
                        respostas_criadas.append(
                            DesafioResposta(
                                partida=partida,
                                questao=questao,
                                alternativa_escolhida=escolha,
                                acertou=acertou,
                            )
                        )
                    DesafioResposta.objects.bulk_create(respostas_criadas)
                    partida.acertos = acertos
                    partida.finalizada_em = agora
                    partida.save(update_fields=("acertos", "finalizada_em"))
                    partida_salva = partida

                    finalizadas = list(
                        DesafioPartida.objects.filter(
                            desafio=desafio, finalizada_em__isnull=False
                        )
                    )
                    if len(finalizadas) == 2:
                        pontos = {item.usuario_id: item.acertos for item in finalizadas}
                        if pontos[desafio.criador_id] == pontos[desafio.convidado_id]:
                            desafio.resultado = DesafioPvP.Resultado.EMPATE
                        elif pontos[desafio.criador_id] > pontos[desafio.convidado_id]:
                            desafio.resultado = DesafioPvP.Resultado.CRIADOR
                        else:
                            desafio.resultado = DesafioPvP.Resultado.CONVIDADO
                        desafio.status = DesafioPvP.Status.CONCLUIDO
                        desafio.concluido_em = agora
                        desafio.save(
                            update_fields=("resultado", "status", "concluido_em")
                        )

    if erro:
        raise ValueError(erro)
    return partida_salva
