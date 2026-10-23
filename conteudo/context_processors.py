from django.urls import reverse
from django.db import transaction
from django.utils import timezone

from .models import Assunto, NotificacaoAluno, Quiz
from .services import notificar_novidade_alunos


def _notificar_publicacoes_agendadas():
    agora = timezone.now()
    materiais = Assunto.objects.filter(
        publicado=True,
        publicar_em__lte=agora,
        notificacao_enviada_em__isnull=True,
    ).select_related("materia")
    for material in materiais:
        with transaction.atomic():
            atualizado = Assunto.objects.filter(
                pk=material.pk, notificacao_enviada_em__isnull=True
            ).update(notificacao_enviada_em=agora)
            if atualizado:
                notificar_novidade_alunos(
                    tipo=NotificacaoAluno.Tipo.MATERIAL,
                    titulo=f"Novo material: {material.titulo}",
                    mensagem=f"{material.materia.nome} - {material.get_serie_display()}",
                    destino=reverse("leitor", args=[material.pk]),
                    serie=material.serie,
                )

    quizzes = Quiz.objects.filter(
        publicado=True,
        publicar_em__lte=agora,
        notificacao_enviada_em__isnull=True,
        questoes__isnull=False,
    ).select_related("materia").distinct()
    for quiz in quizzes:
        with transaction.atomic():
            atualizado = Quiz.objects.filter(
                pk=quiz.pk, notificacao_enviada_em__isnull=True
            ).update(notificacao_enviada_em=agora)
            if atualizado:
                serie = quiz.get_serie_display() if quiz.serie else "Todas as séries"
                notificar_novidade_alunos(
                    tipo=NotificacaoAluno.Tipo.QUIZ,
                    titulo=f"Novo quiz: {quiz.titulo}",
                    mensagem=f"{quiz.materia.nome} - {serie}",
                    destino=reverse("responder_quiz", args=[quiz.pk]),
                    serie=quiz.serie,
                )


def notificacoes_aluno(request):
    _notificar_publicacoes_agendadas()
    nao_lidas = 0
    usuario = request.user
    if usuario.is_authenticated and getattr(usuario, "papel", None) == "aluno":
        nao_lidas = NotificacaoAluno.objects.filter(
            usuario=usuario, lida_em__isnull=True
        ).count()
    return {"notificacoes_nao_lidas": nao_lidas}
