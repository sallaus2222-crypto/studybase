import uuid
import shutil
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.test.utils import override_settings

from contas.models import PerfilAluno, Usuario

from .models import (
    Assunto,
    DesafioPvP,
    ConfiguracaoColagem,
    Marcacao,
    NotaAvaliacao,
    Materia,
    Missao,
    MissaoAluno,
    PerguntaAluno,
    Quiz,
    QuizQuestao,
    QuizTentativa,
    ResultadoRanking,
    RespostaPergunta,
    XPPeriodo,
    XPRegra,
    XPTransacao,
)
from .services import (
    conceder_xp,
    fechar_periodo_ranking,
    processar_missoes,
    resumo_xp,
)
from .arena import aceitar_desafio_pvp, criar_desafio_pvp, registrar_partida_pvp


class PainelProfessorTests(TestCase):
    def setUp(self):
        self.media_temp = Path(settings.BASE_DIR) / "media" / f"test-{uuid.uuid4().hex}"
        self.media_temp.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.media_temp, ignore_errors=True)
        media_override = override_settings(MEDIA_ROOT=self.media_temp)
        media_override.enable()
        self.addCleanup(media_override.disable)
        self.professor = Usuario.objects.create_user(
            username="professora",
            email="professora@example.com",
            password="Senha-forte-123",
            papel=Usuario.Papel.PROFESSOR,
        )
        self.aluno = Usuario.objects.create_user(
            username="estudante",
            email="estudante@example.com",
            password="Senha-forte-123",
            papel=Usuario.Papel.ALUNO,
        )
        self.materia = Materia.objects.create(nome="MatemÃ¡tica")

    def test_aluno_nao_acessa_painel_do_professor(self):
        self.client.force_login(self.aluno)

        resposta = self.client.get(reverse("painel_professor"))

        self.assertEqual(resposta.status_code, 403)

    def test_professor_cria_materia_e_nova_materia_fica_disponivel_nos_assuntos(self):
        self.client.force_login(self.professor)

        resposta = self.client.post(
            reverse("materia_nova"),
            {
                "nome": "História",
                "descricao": "História geral",
                "cor": "#123456",
                "destaque": "on",
                "ordem": "1",
            },
        )

        self.assertRedirects(resposta, reverse("painel_professor"))
        materia = Materia.objects.get(nome="História")
        formulario_assunto = self.client.get(reverse("assunto_novo"))
        self.assertIn(materia, formulario_assunto.context["form"].fields["materia"].queryset)

    def test_aluno_nao_pode_criar_materia_e_nome_duplicado_e_recusado(self):
        self.client.force_login(self.aluno)
        self.assertEqual(self.client.get(reverse("materia_nova")).status_code, 403)

        self.client.force_login(self.professor)
        resposta = self.client.post(
            reverse("materia_nova"),
            {"nome": self.materia.nome, "cor": "#123456", "ordem": "0"},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(Materia.objects.filter(nome=self.materia.nome).count(), 1)

    def test_professor_cria_assunto_com_autoria_no_servidor(self):
        self.client.force_login(self.professor)

        resposta = self.client.post(
            reverse("assunto_novo"),
            {
                "materia": self.materia.pk,
                "serie": "F6",
                "titulo": "FraÃ§Ãµes",
                "conteudo_completo": "Primeiro parÃ¡grafo de leitura.",
                "resumo": "IntroduÃ§Ã£o Ã s fraÃ§Ãµes.",
                "tipo_material": Assunto.TipoMaterial.RESUMO,
                "dificuldade": Assunto.Dificuldade.INTRODUTORIA,
                "ordem": 0,
                "publicado": "on",
            },
        )

        self.assertRedirects(resposta, reverse("painel_professor"))
        assunto = Assunto.objects.get(titulo="FraÃ§Ãµes")
        self.assertEqual(assunto.autor, self.professor)
        self.assertTrue(assunto.publicado)
        self.assertEqual(assunto.conteudo_completo, "Primeiro parÃ¡grafo de leitura.")

    def test_professor_nao_edita_assunto_de_outro_professor(self):
        outro_professor = Usuario.objects.create_user(
            username="outroprofessor",
            email="outro@example.com",
            password="Senha-forte-123",
            papel=Usuario.Papel.PROFESSOR,
        )
        assunto = Assunto.objects.create(
            materia=self.materia,
            serie="F6",
            titulo="ConteÃºdo de outra pessoa",
            autor=outro_professor,
        )
        self.client.force_login(self.professor)

        resposta = self.client.get(
            reverse("assunto_editar", args=[assunto.pk])
        )

        self.assertEqual(resposta.status_code, 404)

    def test_professor_anexa_pdf_e_aluno_conectado_pode_baixar(self):
        self.client.force_login(self.professor)
        resposta = self.client.post(
            reverse("assunto_novo"),
            {
                "materia": self.materia.pk,
                "serie": "F6",
                "titulo": "Guia de fraÃ§Ãµes",
                "tipo_material": Assunto.TipoMaterial.TEXTO,
                "dificuldade": Assunto.Dificuldade.INTRODUTORIA,
                "ordem": 0,
                "publicado": "on",
                "arquivo": SimpleUploadedFile(
                    "guia.pdf", b"%PDF-1.7\nconteudo do teste", content_type="application/pdf"
                ),
            },
        )
        self.assertRedirects(resposta, reverse("painel_professor"))
        assunto = Assunto.objects.get(titulo="Guia de fraÃ§Ãµes")
        self.assertTrue(assunto.arquivo.name.startswith("materiais/"))

        self.client.force_login(self.aluno)
        download = self.client.get(reverse("baixar_material", args=[assunto.pk]))

        self.assertEqual(download.status_code, 200)
        self.assertIn("attachment", download["Content-Disposition"])
        self.assertEqual(download["X-Content-Type-Options"], "nosniff")
        self.assertEqual(b"".join(download.streaming_content), b"%PDF-1.7\nconteudo do teste")
        download.close()

        assunto.publicado = False
        assunto.save(update_fields=("publicado",))
        self.assertEqual(
            self.client.get(reverse("baixar_material", args=[assunto.pk])).status_code,
            404,
        )

    def test_formulario_recusa_arquivo_que_nao_e_pdf_valido(self):
        self.client.force_login(self.professor)
        resposta = self.client.post(
            reverse("assunto_novo"),
            {
                "materia": self.materia.pk,
                "serie": "F6",
                "titulo": "Arquivo invÃ¡lido",
                "tipo_material": Assunto.TipoMaterial.TEXTO,
                "dificuldade": Assunto.Dificuldade.INTRODUTORIA,
                "ordem": 0,
                "publicado": "on",
                "arquivo": SimpleUploadedFile(
                    "arquivo.pdf", b"nao e um PDF", content_type="application/pdf"
                ),
            },
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Assunto.objects.filter(titulo="Arquivo invÃ¡lido").exists())

    def test_caderneta_resume_apenas_quizzes_do_professor_e_filtra_por_serie(self):
        PerfilAluno.objects.create(usuario=self.aluno, serie="F8")
        quiz = Quiz.objects.create(
            materia=self.materia,
            titulo="Revisão de frações",
            serie="F8",
            publicado=True,
            criado_por=self.professor,
        )
        QuizTentativa.objects.create(
            usuario=self.aluno, quiz=quiz, token_envio=uuid.uuid4(),
            total_questoes=10, acertos=8,
        )
        QuizTentativa.objects.create(
            usuario=self.aluno, quiz=quiz, token_envio=uuid.uuid4(),
            total_questoes=10, acertos=10,
        )
        outro_professor = Usuario.objects.create_user(
            username="outro_docente", email="outro_docente@example.com",
            password="Senha-forte-123", papel=Usuario.Papel.PROFESSOR,
        )
        quiz_alheio = Quiz.objects.create(
            materia=self.materia, titulo="Quiz de outra turma", publicado=True,
            criado_por=outro_professor,
        )
        QuizTentativa.objects.create(
            usuario=self.aluno, quiz=quiz_alheio, token_envio=uuid.uuid4(),
            total_questoes=10, acertos=0,
        )

        self.client.force_login(self.professor)
        resposta = self.client.get(reverse("caderneta_professor"), {"serie": "F8"})

        self.assertEqual(resposta.status_code, 200)
        aluno = resposta.context["alunos"].get()
        self.assertEqual(aluno.total_tentativas, 2)
        self.assertEqual(aluno.quizzes_concluidos, 1)
        self.assertEqual(aluno.media_percentual, 90)
        self.assertEqual(len(resposta.context["tentativas_recentes"]), 2)
        self.assertNotContains(resposta, "Quiz de outra turma")

    def test_caderneta_e_restrita_a_professores(self):
        self.client.force_login(self.aluno)

        resposta = self.client.get(reverse("caderneta_professor"))

        self.assertEqual(resposta.status_code, 403)

    def test_professor_lanca_nota_privada_e_nao_pode_editar_nota_alheia(self):
        PerfilAluno.objects.create(usuario=self.aluno, serie="F8")
        outro_aluno = Usuario.objects.create_user(
            username="outro_estudante", email="outro_estudante@example.com",
            password="Senha-forte-123", papel=Usuario.Papel.ALUNO,
        )
        PerfilAluno.objects.create(usuario=outro_aluno, serie="F8")
        self.client.force_login(self.professor)
        enviada = self.client.post(
            reverse("nota_avaliacao_nova"),
            {
                "aluno": self.aluno.pk,
                "materia": self.materia.pk,
                "titulo": "Prova de frações",
                "tipo": NotaAvaliacao.Tipo.PROVA,
                "nota": "7.50",
                "nota_maxima": "10",
                "data_avaliacao": "2026-10-20",
                "observacoes": "Rever simplificação.",
            },
        )
        self.assertRedirects(enviada, reverse("caderneta_professor"))
        nota = NotaAvaliacao.objects.get()
        self.assertEqual(nota.professor, self.professor)
        self.assertEqual(str(nota.nota), "7.50")

        outro_professor = Usuario.objects.create_user(
            username="professora2", email="professora2@example.com",
            password="Senha-forte-123", papel=Usuario.Papel.PROFESSOR,
        )
        self.client.force_login(outro_professor)
        self.assertEqual(
            self.client.get(reverse("nota_avaliacao_editar", args=[nota.pk])).status_code,
            404,
        )

        self.client.force_login(self.aluno)
        minhas = self.client.get(reverse("minhas_notas"))
        self.assertContains(minhas, "Prova de frações")
        self.assertContains(minhas, "7,50")
        self.client.force_login(outro_aluno)
        notas_colega = self.client.get(reverse("minhas_notas"))
        self.assertNotContains(notas_colega, "Prova de frações")

    def test_nota_nao_pode_ultrapassar_pontuacao_maxima(self):
        PerfilAluno.objects.create(usuario=self.aluno, serie="F8")
        self.client.force_login(self.professor)

        resposta = self.client.post(
            reverse("nota_avaliacao_nova"),
            {
                "aluno": self.aluno.pk,
                "materia": self.materia.pk,
                "titulo": "Prova acima do limite",
                "tipo": NotaAvaliacao.Tipo.PROVA,
                "nota": "11",
                "nota_maxima": "10",
                "data_avaliacao": "2026-10-20",
            },
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(NotaAvaliacao.objects.exists())


class BibliotecaTests(TestCase):
    def setUp(self):
        self.aluno = Usuario.objects.create_user(
            username="aluna_biblioteca",
            email="biblioteca@example.com",
            password="Senha-forte-123",
            papel=Usuario.Papel.ALUNO,
        )
        self.materia = Materia.objects.create(nome="CiÃªncias")
        self.resumo = Assunto.objects.create(
            materia=self.materia,
            serie="F7",
            titulo="Ciclo da Ã¡gua",
            resumo="Etapas do ciclo natural.",
            palavras_chave="evaporaÃ§Ã£o, chuva",
            tipo_material=Assunto.TipoMaterial.RESUMO,
            publicado=True,
        )
        Assunto.objects.create(
            materia=self.materia,
            serie="F7",
            titulo="ExercÃ­cios sobre clima",
            tipo_material=Assunto.TipoMaterial.EXERCICIOS,
            publicado=True,
        )
        Assunto.objects.create(
            materia=self.materia,
            serie="F7",
            titulo="Rascunho privado",
            publicado=False,
        )

    def test_aluno_filtra_assuntos_publicados_por_palavra_e_tipo(self):
        self.client.force_login(self.aluno)

        resposta = self.client.get(
            reverse("materia", args=[self.materia.pk]),
            {"serie": "F7", "q": "chuva", "tipo": Assunto.TipoMaterial.RESUMO},
        )

        self.assertEqual(resposta.status_code, 200)
        assuntos = list(resposta.context["assuntos"])
        self.assertEqual(assuntos, [self.resumo])
        self.assertNotContains(resposta, "Rascunho privado")


class PerguntasTests(TestCase):
    def setUp(self):
        self.materia = Materia.objects.create(nome="CiÃªncias das perguntas")
        self.aluno = self.criar_aluno("perguntou", "F8")
        self.colega = self.criar_aluno("colega", "F8")
        self.outra_serie = self.criar_aluno("outra_serie", "F9")
        self.professor = Usuario.objects.create_user(
            username="moderador",
            email="moderador@example.com",
            password="Senha-forte-123",
            papel=Usuario.Papel.PROFESSOR,
        )

    def criar_aluno(self, username, serie):
        usuario = Usuario.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="Senha-forte-123",
            papel=Usuario.Papel.ALUNO,
        )
        PerfilAluno.objects.create(usuario=usuario, serie=serie)
        return usuario

    def criar_pergunta(self):
        return PerguntaAluno.objects.create(
            materia=self.materia,
            serie="F8",
            titulo="Como resolver fraÃ§Ãµes?",
            texto="Podem explicar um exemplo?",
            autor=self.aluno,
        )

    def test_perguntas_e_respostas_exigem_moderacao_e_respeitam_a_serie(self):
        self.client.force_login(self.aluno)
        resposta = self.client.post(
            reverse("perguntas"),
            {
                "materia": self.materia.pk,
                "titulo": "Como resolver fraÃ§Ãµes?",
                "texto": "Podem explicar um exemplo?",
            },
        )
        self.assertRedirects(resposta, reverse("perguntas"))
        pergunta = PerguntaAluno.objects.get(titulo="Como resolver fraÃ§Ãµes?")
        self.assertEqual(pergunta.serie, "F8")
        self.assertEqual(pergunta.status, PerguntaAluno.Status.PENDENTE)

        self.client.force_login(self.colega)
        lista_colega = self.client.get(reverse("perguntas"))
        self.assertNotContains(lista_colega, pergunta.titulo)
        self.assertEqual(
            self.client.get(
                reverse("pergunta_detalhe", args=[pergunta.pk])
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("pergunta_moderar", args=[pergunta.pk]), {"acao": "aprovar"}
            ).status_code,
            403,
        )

        self.client.force_login(self.professor)
        painel = self.client.get(reverse("painel_professor"))
        self.assertContains(painel, pergunta.titulo)
        aprovada = self.client.post(
            reverse("pergunta_moderar", args=[pergunta.pk]), {"acao": "aprovar"}
        )
        self.assertRedirects(aprovada, reverse("painel_professor"))
        pergunta.refresh_from_db()
        self.assertEqual(pergunta.moderada_por, self.professor)
        self.assertIsNotNone(pergunta.moderada_em)

        self.client.force_login(self.colega)
        lista_colega = self.client.get(reverse("perguntas"))
        self.assertContains(lista_colega, pergunta.titulo)
        self.assertNotContains(lista_colega, self.aluno.username)
        detalhe = reverse("pergunta_detalhe", args=[pergunta.pk])
        self.assertEqual(self.client.get(detalhe).status_code, 200)
        self.client.post(detalhe, {"texto": "Uma resposta simples e educativa."})
        resposta_aluno = RespostaPergunta.objects.get(pergunta=pergunta)
        self.assertEqual(resposta_aluno.status, RespostaPergunta.Status.PENDENTE)
        self.client.force_login(self.aluno)
        self.assertNotContains(self.client.get(detalhe), resposta_aluno.texto)

        self.client.force_login(self.professor)
        self.client.post(
            reverse("resposta_moderar", args=[resposta_aluno.pk]),
            {"acao": "aprovar"},
        )
        resposta_aluno.refresh_from_db()
        self.assertEqual(resposta_aluno.status, RespostaPergunta.Status.APROVADA)

        self.client.force_login(self.aluno)
        self.assertContains(self.client.get(detalhe), resposta_aluno.texto)
        self.client.force_login(self.outra_serie)
        self.assertEqual(self.client.get(detalhe).status_code, 404)

    def test_aluno_nao_pode_enviar_resposta_para_a_propria_pergunta(self):
        pergunta = self.criar_pergunta()
        pergunta.status = PerguntaAluno.Status.APROVADA
        pergunta.save(update_fields=("status",))
        self.client.force_login(self.aluno)

        resposta = self.client.post(
            reverse("pergunta_detalhe", args=[pergunta.pk]),
            {"texto": "Vou responder a mim mesmo."},
        )

        self.assertEqual(resposta.status_code, 400)
        self.assertFalse(RespostaPergunta.objects.filter(pergunta=pergunta).exists())

    def test_professor_pode_rejeitar_pergunta_sem_publica_la(self):
        pergunta = self.criar_pergunta()
        self.client.force_login(self.professor)

        resposta = self.client.post(
            reverse("pergunta_moderar", args=[pergunta.pk]), {"acao": "rejeitar"}
        )

        self.assertRedirects(resposta, reverse("painel_professor"))
        pergunta.refresh_from_db()
        self.assertEqual(pergunta.status, PerguntaAluno.Status.REJEITADA)
        self.assertEqual(pergunta.moderada_por, self.professor)
        self.client.force_login(self.colega)
        self.assertNotContains(self.client.get(reverse("perguntas")), pergunta.titulo)


class LeitorEMarcacoesTests(TestCase):
    def setUp(self):
        self.aluna = Usuario.objects.create_user(
            username="leitora",
            email="leitora@example.com",
            password="Senha-forte-123",
            papel=Usuario.Papel.ALUNO,
        )
        self.outro_aluno = Usuario.objects.create_user(
            username="outra_leitora",
            email="outra@example.com",
            password="Senha-forte-123",
            papel=Usuario.Papel.ALUNO,
        )
        self.materia = Materia.objects.create(nome="HistÃ³ria")
        self.assunto = Assunto.objects.create(
            materia=self.materia,
            serie="F8",
            titulo="CivilizaÃ§Ãµes antigas",
            resumo="IntroduÃ§Ã£o ao tema.",
            conteudo_completo=(
                "As primeiras cidades surgiram perto dos rios.\n\n"
                "A agricultura ajudou essas comunidades a crescer."
            ),
            publicado=True,
        )

    def test_aluno_abre_leitor_e_cria_marcacao_no_proprio_perfil(self):
        self.client.force_login(self.aluna)
        url_leitor = reverse("leitor", args=[self.assunto.pk])
        resposta_leitor = self.client.get(url_leitor)
        trecho_id = resposta_leitor.context["secoes"][0]["id"]

        resposta = self.client.post(
            reverse("marcacao_nova", args=[self.assunto.pk]),
            {
                "trecho_id": trecho_id,
                "trecho_texto": "cidades surgiram perto dos rios",
                "cor": "amarelo",
                "etiqueta": "Geografia",
                "anotacao": "Rever esta relaÃ§Ã£o.",
            },
        )

        self.assertEqual(resposta.status_code, 302)
        marcacao = Marcacao.objects.get()
        self.assertEqual(marcacao.usuario, self.aluna)
        self.assertEqual(marcacao.assunto, self.assunto)
        self.assertContains(
            self.client.get(url_leitor), "Rever esta relaÃ§Ã£o."
        )

    def test_marcacao_nao_pode_apontar_para_trecho_de_outro_conteudo(self):
        self.client.force_login(self.aluna)

        resposta = self.client.post(
            reverse("marcacao_nova", args=[self.assunto.pk]),
            {
                "trecho_id": "trecho-inexistente",
                "trecho_texto": "texto inventado",
                "cor": "amarelo",
                "etiqueta": "",
                "anotacao": "",
            },
        )

        self.assertEqual(resposta.status_code, 400)
        self.assertFalse(Marcacao.objects.exists())

    def test_aluno_nao_ve_nem_apaga_marcacao_de_outra_pessoa(self):
        self.client.force_login(self.aluna)
        secao = self.client.get(
            reverse("leitor", args=[self.assunto.pk])
        ).context["secoes"][0]
        marcacao = Marcacao.objects.create(
            usuario=self.aluna,
            assunto=self.assunto,
            trecho_id=secao["id"],
            trecho_texto="As primeiras cidades",
        )
        self.client.force_login(self.outro_aluno)

        resposta_lista = self.client.get(reverse("minhas_marcacoes"))
        resposta_excluir = self.client.post(
            reverse(
                "marcacao_excluir", args=[self.assunto.pk, marcacao.pk]
            )
        )

        self.assertEqual(resposta_lista.status_code, 200)
        self.assertNotContains(resposta_lista, "As primeiras cidades")
        self.assertEqual(resposta_excluir.status_code, 404)
        self.assertTrue(Marcacao.objects.filter(pk=marcacao.pk).exists())


class QuizTests(TestCase):
    def setUp(self):
        self.aluno = Usuario.objects.create_user(
            username="aluno_quiz",
            email="quiz@example.com",
            password="Senha-forte-123",
            papel=Usuario.Papel.ALUNO,
        )
        self.outro_aluno = Usuario.objects.create_user(
            username="outro_aluno_quiz",
            email="outro-quiz@example.com",
            password="Senha-forte-123",
            papel=Usuario.Papel.ALUNO,
        )
        self.professor = Usuario.objects.create_user(
            username="professor_quiz",
            email="professor-quiz@example.com",
            password="Senha-forte-123",
            papel=Usuario.Papel.PROFESSOR,
        )
        self.materia = Materia.objects.create(nome="Astronomia")
        self.quiz = Quiz.objects.create(
            materia=self.materia,
            titulo="Planetas",
            descricao="Quiz sobre o sistema solar.",
            publicado=True,
        )
        self.questao = QuizQuestao.objects.create(
            quiz=self.quiz,
            enunciado="Qual planeta Ã© conhecido como planeta vermelho?",
            alternativa_a="VÃªnus",
            alternativa_b="Marte",
            alternativa_c="JÃºpiter",
            alternativa_d="MercÃºrio",
            resposta_correta="B",
            explicacao="A superfÃ­cie de Marte tem Ã³xidos de ferro.",
        )

    def test_resposta_correta_so_aparece_depois_do_envio_e_repeticao_nao_duplica(self):
        XPRegra.objects.create(atividade="quiz", xp=25, ativa=True)
        self.client.force_login(self.aluno)
        url = reverse("responder_quiz", args=[self.quiz.pk])
        resposta_get = self.client.get(url)
        token = resposta_get.context["token_envio"]

        self.assertEqual(resposta_get.status_code, 200)
        self.assertNotIn("resposta_correta", resposta_get.context["questoes"][0])
        self.assertNotContains(resposta_get, "A superfÃ­cie de Marte")

        dados = {"token_envio": str(token), f"resposta_{self.questao.pk}": "B"}
        resposta_post = self.client.post(url, dados)
        resposta_repetida = self.client.post(url, dados)

        self.assertEqual(resposta_post.status_code, 302)
        self.assertEqual(resposta_repetida.status_code, 302)
        self.assertEqual(QuizTentativa.objects.count(), 1)
        self.assertEqual(XPTransacao.objects.count(), 1)
        tentativa = QuizTentativa.objects.get()
        self.assertEqual(tentativa.acertos, 1)
        self.assertEqual(resumo_xp(self.aluno)["xp_vitalicio"], 25)
        resultado = self.client.get(
            reverse("resultado_quiz", args=[tentativa.pk])
        )
        historico = self.client.get(reverse("quizzes"))
        self.assertContains(resultado, "Resposta correta")
        self.assertEqual(len(historico.context["tentativas"]), 1)

    def test_quiz_sem_regra_ativa_nao_concede_xp(self):
        self.client.force_login(self.aluno)
        url = reverse("responder_quiz", args=[self.quiz.pk])
        resposta_get = self.client.get(url)
        resposta = self.client.post(
            url,
            {
                "token_envio": str(resposta_get.context["token_envio"]),
                f"resposta_{self.questao.pk}": "B",
            },
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(XPTransacao.objects.exists())

    def test_resultado_de_tentativa_e_privado_para_o_dono(self):
        tentativa = QuizTentativa.objects.create(
            usuario=self.aluno,
            quiz=self.quiz,
            token_envio=uuid.uuid4(),
            total_questoes=1,
            acertos=0,
        )
        self.client.force_login(self.outro_aluno)

        resposta = self.client.get(
            reverse("resultado_quiz", args=[tentativa.pk])
        )

        self.assertEqual(resposta.status_code, 404)

    def test_professor_nao_pode_responder_quiz_de_aluno(self):
        self.client.force_login(self.professor)

        resposta = self.client.get(reverse("quizzes"))

        self.assertEqual(resposta.status_code, 403)

    def test_aluno_pode_acessar_quiz_de_outra_serie(self):
        PerfilAluno.objects.create(usuario=self.aluno, serie=PerfilAluno.Serie.F6)
        quiz_medio = Quiz.objects.create(
            materia=self.materia,
            titulo="Quiz de outra sÃ©rie",
            serie=PerfilAluno.Serie.M1,
            publicado=True,
        )
        QuizQuestao.objects.create(
            quiz=quiz_medio,
            enunciado="QuestÃ£o de outra sÃ©rie",
            alternativa_a="A",
            alternativa_b="B",
            alternativa_c="C",
            alternativa_d="D",
            resposta_correta="A",
        )
        self.client.force_login(self.aluno)

        lista = self.client.get(reverse("quizzes"))
        resposta = self.client.get(reverse("responder_quiz", args=[quiz_medio.pk]))

        self.assertContains(lista, "Quiz de outra sÃ©rie")
        self.assertEqual(resposta.status_code, 200)


class QuizArenaTests(TestCase):
    def setUp(self):
        self.materia = Materia.objects.create(nome="MatemÃ¡tica Arena")
        self.criador = self.criar_aluno("arena_criador", "F8")
        self.convidado = self.criar_aluno("arena_convidado", "F8")
        self.outra_serie = self.criar_aluno("arena_outra_serie", "M1")
        self.quiz = Quiz.objects.create(
            materia=self.materia,
            titulo="Quiz de dez questÃµes",
            serie="F8",
            publicado=True,
        )
        for ordem in range(1, 11):
            QuizQuestao.objects.create(
                quiz=self.quiz,
                enunciado=f"QuestÃ£o {ordem}",
                alternativa_a="OpÃ§Ã£o A",
                alternativa_b="OpÃ§Ã£o B",
                alternativa_c="OpÃ§Ã£o C",
                alternativa_d="OpÃ§Ã£o D",
                resposta_correta="ABCD"[(ordem - 1) % 4],
                ordem=ordem,
            )

    def criar_aluno(self, username, serie):
        usuario = Usuario.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="Senha-forte-123",
            papel=Usuario.Papel.ALUNO,
        )
        PerfilAluno.objects.create(usuario=usuario, serie=serie)
        return usuario

    def respostas_corretas(self):
        return {
            questao.ordem: questao.resposta_correta
            for questao in DesafioPvP.objects.get().questoes.all()
        }

    def test_desafio_exige_dez_questoes_e_encerra_apos_os_dois_envios(self):
        self.client.force_login(self.criador)
        criacao = self.client.post(reverse("arena"), {"quiz": self.quiz.pk})
        desafio = DesafioPvP.objects.get(criador=self.criador)
        self.assertRedirects(
            criacao, reverse("arena_desafio", args=[desafio.convite])
        )
        self.assertEqual(desafio.questoes.count(), 10)
        self.assertLess(
            abs(desafio.expira_em - desafio.criado_em - timedelta(hours=48)),
            timedelta(seconds=1),
        )
        self.client.force_login(self.convidado)
        convite = self.client.get(reverse("arena_desafio", args=[desafio.convite]))
        self.assertContains(convite, "Aceitar desafio")
        self.assertNotContains(convite, self.criador.username)

        self.client.force_login(self.outra_serie)
        self.assertEqual(
            self.client.get(reverse("arena_desafio", args=[desafio.convite])).status_code,
            404,
        )
        self.client.force_login(self.convidado)
        aceitou = self.client.post(
            reverse("arena_aceitar", args=[desafio.convite])
        )
        self.assertRedirects(
            aceitou, reverse("arena_desafio", args=[desafio.convite])
        )

        desafio.refresh_from_db()
        respostas = self.respostas_corretas()
        respostas_form = {f"resposta_{ordem}": valor for ordem, valor in respostas.items()}
        self.client.force_login(self.criador)
        envio_criador = self.client.post(
            reverse("arena_desafio", args=[desafio.convite]), respostas_form
        )
        self.assertRedirects(
            envio_criador, reverse("arena_desafio", args=[desafio.convite])
        )
        desafio.refresh_from_db()
        self.assertEqual(desafio.status, DesafioPvP.Status.EM_ANDAMENTO)
        pagina_aguardando = self.client.get(
            reverse("arena_desafio", args=[desafio.convite])
        )
        self.assertContains(pagina_aguardando, "Respostas registradas")
        self.assertNotContains(pagina_aguardando, "10/10")

        respostas_convidado = dict(respostas_form)
        respostas_convidado["resposta_10"] = (
            "B" if respostas[10] != "B" else "A"
        )
        self.client.force_login(self.convidado)
        envio_convidado = self.client.post(
            reverse("arena_desafio", args=[desafio.convite]), respostas_convidado
        )
        self.assertRedirects(
            envio_convidado, reverse("arena_desafio", args=[desafio.convite])
        )

        desafio.refresh_from_db()
        self.assertEqual(desafio.status, DesafioPvP.Status.CONCLUIDO)
        self.assertEqual(desafio.resultado, DesafioPvP.Resultado.CRIADOR)
        pontuacoes = {
            partida.usuario_id: partida.acertos
            for partida in desafio.partidas.all()
        }
        self.assertEqual(pontuacoes[self.criador.pk], 10)
        self.assertEqual(pontuacoes[self.convidado.pk], 9)
        self.assertFalse(XPTransacao.objects.exists())
        resultado = self.client.get(reverse("arena_desafio", args=[desafio.convite]))
        self.assertContains(resultado, "Seu advers")
        self.assertContains(resultado, "9/10")

    def test_convite_nao_pode_ser_aceito_pelo_criador_ou_por_outra_serie(self):
        desafio = criar_desafio_pvp(self.criador, self.quiz)
        with self.assertRaises(ValueError):
            aceitar_desafio_pvp(desafio.pk, self.criador)
        with self.assertRaises(ValueError):
            aceitar_desafio_pvp(desafio.pk, self.outra_serie)
        desafio.refresh_from_db()
        self.assertEqual(desafio.status, DesafioPvP.Status.ABERTO)

    def test_convite_expira_e_nao_pode_ser_aceito_depois_do_prazo(self):
        desafio = criar_desafio_pvp(self.criador, self.quiz)
        with self.assertRaises(ValueError):
            aceitar_desafio_pvp(
                desafio.pk,
                self.convidado,
                agora=desafio.expira_em + timedelta(seconds=1),
            )
        desafio.refresh_from_db()
        self.assertEqual(desafio.status, DesafioPvP.Status.EXPIRADO)

    def test_partidas_com_a_mesma_pontuacao_terminam_empate(self):
        desafio = criar_desafio_pvp(self.criador, self.quiz)
        aceitar_desafio_pvp(desafio.pk, self.convidado)
        respostas = {
            questao.ordem: questao.resposta_correta
            for questao in desafio.questoes.all()
        }

        registrar_partida_pvp(desafio.pk, self.criador, respostas)
        registrar_partida_pvp(desafio.pk, self.convidado, respostas)

        desafio.refresh_from_db()
        self.assertEqual(desafio.status, DesafioPvP.Status.CONCLUIDO)
        self.assertEqual(desafio.resultado, DesafioPvP.Resultado.EMPATE)


class XPServiceTests(TestCase):
    def setUp(self):
        self.aluno = Usuario.objects.create_user(
            username="aluno_xp",
            email="xp@example.com",
            password="Senha-forte-123",
            papel=Usuario.Papel.ALUNO,
        )
        self.regra = XPRegra.objects.create(atividade="quiz", xp=18, ativa=True)

    def test_xp_e_idempotente_e_separado_por_temporada_e_ano(self):
        primeira = conceder_xp(
            self.aluno, "quiz", "atividade-dezembro", "Quiz de teste", date(2025, 12, 31)
        )
        repetida = conceder_xp(
            self.aluno, "quiz", "atividade-dezembro", "Quiz de teste", date(2026, 1, 1)
        )
        janeiro = conceder_xp(
            self.aluno, "quiz", "atividade-janeiro", "Outro quiz", date(2026, 1, 1)
        )

        self.assertEqual(primeira.pk, repetida.pk)
        self.assertNotEqual(primeira.temporada_id, janeiro.temporada_id)
        self.assertNotEqual(primeira.periodo_anual_id, janeiro.periodo_anual_id)
        resumo_2025 = resumo_xp(self.aluno, date(2025, 12, 31))
        resumo_2026 = resumo_xp(self.aluno, date(2026, 1, 1))
        self.assertEqual(resumo_2025["xp_temporada"], 18)
        self.assertEqual(resumo_2025["xp_anual"], 18)
        self.assertEqual(resumo_2026["xp_temporada"], 18)
        self.assertEqual(resumo_2026["xp_anual"], 18)
        self.assertEqual(resumo_2026["xp_vitalicio"], 36)
        self.assertEqual(XPTransacao.objects.count(), 2)


class FechamentoRankingTests(TestCase):
    def setUp(self):
        self.regra = XPRegra.objects.create(atividade="quiz", xp=12, ativa=True)
        self.alunos = []
        for nome, serie, pontos in (
            ("aluno_f6", "F6", 12),
            ("aluno_f9", "F9", 24),
            ("aluno_m1", "M1", 36),
            ("aluno_f7", "F7", 12),
        ):
            usuario = Usuario.objects.create_user(
                username=nome,
                email=f"{nome}@example.com",
                password="Senha-forte-123",
                papel=Usuario.Papel.ALUNO,
            )
            PerfilAluno.objects.create(
                usuario=usuario,
                serie=serie,
                participar_ranking=True,
                apelido_ranking=f"Apelido-{nome}",
            )
            self.regra.xp = pontos
            self.regra.save()
            conceder_xp(usuario, "quiz", nome, "Quiz concluÃ­do", date(2025, 12, 20))
            self.alunos.append(usuario)

    def test_fechar_periodo_salva_ranks_uma_vez_e_impede_novos_xp(self):
        periodo = XPPeriodo.objects.get(tipo=XPPeriodo.Tipo.TEMPORADA, chave="2025-12")

        resultados = fechar_periodo_ranking(periodo, hoje=date(2026, 1, 1))
        repetidos = fechar_periodo_ranking(periodo, hoje=date(2026, 1, 1))

        self.assertTrue(periodo.__class__.objects.get(pk=periodo.pk).fechado)
        self.assertEqual(len(resultados), 8)
        self.assertEqual(len(repetidos), 8)
        global_resultados = list(
            ResultadoRanking.objects.filter(periodo=periodo, categoria="global")
        )
        self.assertEqual(
            sorted((item.posicao, item.apelido, item.xp) for item in global_resultados),
            [
                (1, "Apelido-aluno_m1", 36),
                (2, "Apelido-aluno_f9", 24),
                (3, "Apelido-aluno_f6", 12),
                (3, "Apelido-aluno_f7", 12),
            ],
        )

        perfil = self.alunos[0].perfil_aluno
        perfil.apelido_ranking = "Apelido alterado"
        perfil.save(update_fields=("apelido_ranking",))
        self.assertEqual(
            ResultadoRanking.objects.get(
                periodo=periodo,
                categoria="global",
                apelido="Apelido-aluno_f6",
            ).apelido,
            "Apelido-aluno_f6",
        )
        self.assertIsNone(
            conceder_xp(
                self.alunos[0], "quiz", "depois-do-fechamento", "Quiz tardio", date(2025, 12, 21)
            )
        )

        periodo_anual = XPPeriodo.objects.get(
            tipo=XPPeriodo.Tipo.ANUAL, chave="2025"
        )
        fechamento_anual = fechar_periodo_ranking(
            periodo_anual, hoje=date(2026, 1, 1)
        )
        self.assertTrue(periodo_anual.__class__.objects.get(pk=periodo_anual.pk).fechado)
        self.assertEqual(len(fechamento_anual), 8)

    def test_periodo_em_andamento_nao_pode_ser_encerrado(self):
        periodo = XPPeriodo.objects.get(tipo=XPPeriodo.Tipo.TEMPORADA, chave="2025-12")
        with self.assertRaises(ValueError):
            fechar_periodo_ranking(periodo, hoje=date(2025, 12, 31))
        periodo.refresh_from_db()
        self.assertFalse(periodo.fechado)


class MissaoServiceTests(TestCase):
    def setUp(self):
        self.aluno = Usuario.objects.create_user(
            username="aluno_missao",
            email="missao@example.com",
            password="Senha-forte-123",
            papel=Usuario.Papel.ALUNO,
        )
        self.quiz = Quiz.objects.create(
            materia=Materia.objects.create(nome="CiÃªncias da missÃ£o"),
            titulo="Quiz da missÃ£o",
            publicado=True,
        )

    def criar_tentativa(self, acertos=1, total=1):
        return QuizTentativa.objects.create(
            usuario=self.aluno,
            quiz=self.quiz,
            token_envio=uuid.uuid4(),
            total_questoes=total,
            acertos=acertos,
        )

    def test_missao_concede_recompensa_uma_vez_ao_atingir_meta(self):
        missao = Missao.objects.create(
            nome="Praticar dois quizzes",
            criterio=Missao.Criterio.QUIZZES_CONCLUIDOS,
            meta=2,
            recompensa_xp=15,
            ativa=True,
        )
        self.criar_tentativa()
        self.criar_tentativa(acertos=0)

        processar_missoes(self.aluno)
        processar_missoes(self.aluno)

        participacao = MissaoAluno.objects.get(usuario=self.aluno, missao=missao)
        transacoes = XPTransacao.objects.filter(
            usuario=self.aluno, origem="missao", missao=missao
        )
        self.assertIsNotNone(participacao.concluida_em)
        self.assertEqual(participacao.progresso, 2)
        self.assertEqual(transacoes.count(), 1)
        self.assertEqual(transacoes.get().xp, 15)
        self.assertIsNone(transacoes.get().regra)

    def test_missao_de_quiz_perfeito_ignora_tentativa_com_erro(self):
        missao = Missao.objects.create(
            nome="Acerto perfeito",
            criterio=Missao.Criterio.QUIZZES_PERFEITOS,
            meta=1,
            ativa=True,
        )
        self.criar_tentativa(acertos=0)

        processar_missoes(self.aluno)

        participacao = MissaoAluno.objects.get(usuario=self.aluno, missao=missao)
        self.assertEqual(participacao.progresso, 0)
        self.assertIsNone(participacao.concluida_em)

        self.criar_tentativa(acertos=1)
        processar_missoes(self.aluno)

        participacao.refresh_from_db()
        self.assertEqual(participacao.progresso, 1)
        self.assertIsNotNone(participacao.concluida_em)


class ConfiguracaoColagemTests(TestCase):
    def setUp(self):
        self.professor = Usuario.objects.create_user(
            username="config_professor",
            email="config_professor@example.com",
            password="Senha-forte-123",
            papel=Usuario.Papel.PROFESSOR,
        )
        self.admin = Usuario.objects.create_user(
            username="config_admin",
            email="config_admin@example.com",
            password="Senha-forte-123",
            papel=Usuario.Papel.ADMIN,
        )
        self.aluno = Usuario.objects.create_user(
            username="config_aluno",
            email="config_aluno@example.com",
            password="Senha-forte-123",
            papel=Usuario.Papel.ALUNO,
        )
        PerfilAluno.objects.create(usuario=self.aluno, serie="F8")

    def test_professor_e_admin_controlam_flags_independentes(self):
        self.client.force_login(self.professor)
        ligado_professor = self.client.post(
            reverse("configuracao_colagem_professor"),
            {"bloquear_colagem_professor": "on"},
        )
        self.assertRedirects(
            ligado_professor, reverse("configuracao_colagem_professor")
        )
        configuracao = ConfiguracaoColagem.objects.get(pk=1)
        self.assertTrue(configuracao.bloqueio_ativo)

        self.client.force_login(self.admin)
        ligado_admin = self.client.post(
            reverse("configuracao_colagem_admin"),
            {"bloquear_colagem_admin": "on"},
        )
        self.assertRedirects(ligado_admin, reverse("configuracao_colagem_admin"))

        self.client.force_login(self.professor)
        self.client.post(reverse("configuracao_colagem_professor"), {})
        configuracao.refresh_from_db()
        self.assertFalse(configuracao.bloquear_colagem_professor)
        self.assertTrue(configuracao.bloqueio_ativo)

        self.client.force_login(self.admin)
        self.client.post(reverse("configuracao_colagem_admin"), {})
        configuracao.refresh_from_db()
        self.assertFalse(configuracao.bloqueio_ativo)

    def test_bloqueio_se_aplica_aos_formularios_dos_alunos_e_permissoes_sao_separadas(self):
        self.client.force_login(self.professor)
        self.assertEqual(
            self.client.get(reverse("configuracao_colagem_admin")).status_code,
            403,
        )
        self.client.force_login(self.aluno)
        self.assertEqual(
            self.client.get(reverse("configuracao_colagem_professor")).status_code,
            403,
        )

        ConfiguracaoColagem.objects.create(pk=1, bloquear_colagem_admin=True)
        pagina = self.client.get(reverse("perguntas"))
        self.assertContains(pagina, 'data-bloquear-colagem="true"')
        self.assertContains(pagina, "bloqueio_colagem.js")
