from io import BytesIO
import uuid

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.test.utils import override_settings
from PIL import Image

from conteudo.models import (
    Materia,
    ResultadoRanking,
    Titulo,
    TituloConcedido,
    XPPeriodo,
    XPRegra,
)
from conteudo.services import conceder_xp

from .models import CodigoProfessor, PerfilAluno, Usuario


class CadastroTests(TestCase):
    def test_cadastro_de_aluno_cria_perfil_e_guarda_confirmacao(self):
        resposta = self.client.post(
            reverse("cadastro"),
            {
                "username": "aluna",
                "email": "aluna@example.com",
                "serie": "F8",
                "escola_autorizou": "on",
                "password1": "UmaSenhaForte-123",
                "password2": "UmaSenhaForte-123",
            },
        )

        self.assertRedirects(resposta, reverse("inicio"))
        usuario = Usuario.objects.get(username="aluna")
        perfil = PerfilAluno.objects.get(usuario=usuario)
        self.assertEqual(perfil.serie, "F8")
        self.assertTrue(perfil.escola_autorizou)
        self.assertIsNotNone(perfil.escola_autorizou_em)

    def test_cadastro_de_professor_usa_codigo_valido_e_hash(self):
        codigo = CodigoProfessor()
        codigo.definir_codigo("CHAVE-DA-DIRECAO")
        codigo.save()

        resposta = self.client.post(
            reverse("cadastro_professor"),
            {
                "username": "professor",
                "email": "professor@example.com",
                "codigo_professor": "CHAVE-DA-DIRECAO",
                "password1": "UmaSenhaForte-123",
                "password2": "UmaSenhaForte-123",
            },
        )

        self.assertRedirects(resposta, reverse("inicio"))
        usuario = Usuario.objects.get(username="professor")
        self.assertEqual(usuario.papel, Usuario.Papel.PROFESSOR)
        self.assertNotEqual(codigo.codigo_hash, "CHAVE-DA-DIRECAO")
        self.assertTrue(codigo.confere("CHAVE-DA-DIRECAO"))

    def test_cadastro_de_professor_rejeita_codigo_invalido(self):
        resposta = self.client.post(
            reverse("cadastro_professor"),
            {
                "username": "tentativa",
                "email": "tentativa@example.com",
                "codigo_professor": "CODIGO-ERRADO",
                "password1": "UmaSenhaForte-123",
                "password2": "UmaSenhaForte-123",
            },
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Usuario.objects.filter(username="tentativa").exists())


class InicioTests(TestCase):
    def setUp(self):
        self.aluno = Usuario.objects.create_user(
            username="estudante",
            email="estudante@example.com",
            password="Senha-forte-123",
            papel=Usuario.Papel.ALUNO,
        )
        PerfilAluno.objects.create(usuario=self.aluno, serie="M2")

    def test_inicio_exige_login(self):
        resposta = self.client.get(reverse("inicio"))

        self.assertRedirects(
            resposta, f"{reverse('login')}?next={reverse('inicio')}"
        )

    def test_inicio_lista_materias_em_destaque(self):
        em_destaque = Materia.objects.create(nome="Biologia", destaque=True)
        Materia.objects.create(nome="História", destaque=False)
        self.client.force_login(self.aluno)

        resposta = self.client.get(reverse("inicio"))

        self.assertContains(resposta, "Biologia")
        self.assertContains(resposta, "2º ano (Médio)")
        self.assertNotContains(resposta, "História")
        self.assertEqual(list(resposta.context["materias_destaque"]), [em_destaque])

    def test_inicio_mostra_titulo_ativo_do_aluno(self):
        titulo = Titulo.objects.create(nome="Explorador do conhecimento")
        TituloConcedido.objects.create(
            usuario=self.aluno, titulo=titulo, ativo=True
        )
        self.client.force_login(self.aluno)

        resposta = self.client.get(reverse("inicio"))

        self.assertContains(resposta, "Explorador do conhecimento")

    def test_inicio_do_professor_tem_atalho_para_painel(self):
        professor = Usuario.objects.create_user(
            username="professora",
            email="professora@example.com",
            password="Senha-forte-123",
            papel=Usuario.Papel.PROFESSOR,
        )
        self.client.force_login(professor)

        resposta = self.client.get(reverse("inicio"))

        self.assertContains(resposta, reverse("painel_professor"))
        self.assertContains(resposta, "Professor")


class PerfilAlunoTests(TestCase):
    def setUp(self):
        self.aluno = Usuario.objects.create_user(
            username="aluno",
            email="aluno@example.com",
            password="Senha-forte-123",
            papel=Usuario.Papel.ALUNO,
        )
        self.perfil = PerfilAluno.objects.create(usuario=self.aluno, serie="F7")

    def test_aluno_pode_atualizar_nome_de_exibicao_e_avatar(self):
        self.client.force_login(self.aluno)

        resposta = self.client.post(
            reverse("perfil"),
            {"nome_exibicao": "Estrela", "avatar": PerfilAluno.Avatar.OCEANO},
        )

        self.assertRedirects(resposta, reverse("perfil"))
        self.perfil.refresh_from_db()
        self.assertEqual(self.perfil.nome_exibicao, "Estrela")
        self.assertEqual(self.perfil.avatar, PerfilAluno.Avatar.OCEANO)

    def test_professor_nao_edita_perfil_de_aluno(self):
        professor = Usuario.objects.create_user(
            username="professor",
            email="professor@example.com",
            password="Senha-forte-123",
            papel=Usuario.Papel.PROFESSOR,
        )
        self.client.force_login(professor)

        resposta = self.client.get(reverse("perfil"))

        self.assertEqual(resposta.status_code, 403)


class FotoPerfilTests(TestCase):
    def setUp(self):
        self.media_settings = override_settings(
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.InMemoryStorage"
                },
                "staticfiles": {
                    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
                },
            }
        )
        self.media_settings.enable()
        self.aluno = Usuario.objects.create_user(
            username="dona_foto",
            email="dona@example.com",
            password="Senha-forte-123",
            papel=Usuario.Papel.ALUNO,
        )
        self.perfil = PerfilAluno.objects.create(usuario=self.aluno, serie="F8")
        self.outro_aluno = Usuario.objects.create_user(
            username="outro_aluno",
            email="outro-aluno@example.com",
            password="Senha-forte-123",
            papel=Usuario.Papel.ALUNO,
        )
        PerfilAluno.objects.create(usuario=self.outro_aluno, serie="F8")

    def tearDown(self):
        self.media_settings.disable()

    def criar_png(self):
        buffer = BytesIO()
        Image.new("RGB", (64, 48), color=(30, 120, 200)).save(buffer, format="PNG")
        return SimpleUploadedFile(
            "minha-foto.png", buffer.getvalue(), content_type="image/png"
        )

    def test_aluno_envia_foto_e_so_ele_a_acessa_por_padrao(self):
        self.client.force_login(self.aluno)

        resposta = self.client.post(
            reverse("perfil"),
            {
                "nome_exibicao": "Dona da foto",
                "avatar": PerfilAluno.Avatar.AURORA,
                "foto": self.criar_png(),
            },
        )

        self.assertRedirects(resposta, reverse("perfil"))
        self.perfil.refresh_from_db()
        self.assertTrue(self.perfil.foto.name.endswith(".png"))
        self.assertEqual(
            self.client.get(reverse("foto_perfil", args=[self.aluno.pk])).status_code,
            200,
        )
        self.client.force_login(self.outro_aluno)
        self.assertEqual(
            self.client.get(reverse("foto_perfil", args=[self.aluno.pk])).status_code,
            404,
        )

    def test_foto_publica_so_fica_visivel_para_usuario_conectado(self):
        self.perfil.foto = self.criar_png()
        self.perfil.foto_publica = True
        self.perfil.save()
        self.client.force_login(self.outro_aluno)

        resposta = self.client.get(reverse("foto_perfil", args=[self.aluno.pk]))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Cache-Control"], "private, no-store")

    def test_upload_recusa_arquivo_que_nao_e_imagem(self):
        self.client.force_login(self.aluno)

        resposta = self.client.post(
            reverse("perfil"),
            {
                "nome_exibicao": "Dona da foto",
                "avatar": PerfilAluno.Avatar.AURORA,
                "foto": SimpleUploadedFile(
                    "nao-e-imagem.png", b"conteudo invalido", content_type="image/png"
                ),
            },
        )

        self.assertEqual(resposta.status_code, 200)
        self.perfil.refresh_from_db()
        self.assertFalse(self.perfil.foto)

    def test_aluno_envia_imagem_de_fundo_privada_e_aparece_na_pagina_inicial(self):
        self.client.force_login(self.aluno)

        resposta = self.client.post(
            reverse("perfil"),
            {
                "nome_exibicao": "Dona da foto",
                "avatar": PerfilAluno.Avatar.AURORA,
                "imagem_fundo": self.criar_png(),
            },
        )

        self.assertRedirects(resposta, reverse("perfil"))
        self.perfil.refresh_from_db()
        self.assertTrue(self.perfil.imagem_fundo.name.endswith(".png"))
        resposta_fundo = self.client.get(reverse("imagem_fundo_perfil"))
        self.assertEqual(resposta_fundo.status_code, 200)
        self.assertEqual(resposta_fundo["Content-Type"], "image/png")
        self.assertEqual(resposta_fundo["Cache-Control"], "private, no-store")
        self.assertContains(
            self.client.get(reverse("inicio")),
            reverse("imagem_fundo_perfil"),
        )

        resposta = self.client.post(
            reverse("perfil"),
            {
                "nome_exibicao": "Dona da foto",
                "avatar": PerfilAluno.Avatar.AURORA,
                "remover_imagem_fundo": "on",
            },
        )
        self.assertRedirects(resposta, reverse("perfil"))
        self.perfil.refresh_from_db()
        self.assertFalse(self.perfil.imagem_fundo)
        self.assertEqual(
            self.client.get(reverse("imagem_fundo_perfil")).status_code, 404
        )

        self.client.force_login(self.outro_aluno)
        self.assertEqual(
            self.client.get(reverse("imagem_fundo_perfil")).status_code, 404
        )

    def test_upload_recusa_arquivo_invalido_como_imagem_de_fundo(self):
        self.client.force_login(self.aluno)

        resposta = self.client.post(
            reverse("perfil"),
            {
                "nome_exibicao": "Dona da foto",
                "avatar": PerfilAluno.Avatar.AURORA,
                "imagem_fundo": SimpleUploadedFile(
                    "nao-e-imagem.png", b"conteudo invalido", content_type="image/png"
                ),
            },
        )

        self.assertEqual(resposta.status_code, 200)
        self.perfil.refresh_from_db()
        self.assertFalse(self.perfil.imagem_fundo)


class RankingTests(TestCase):
    def setUp(self):
        self.alunos = {}
        for nome, serie, pontos in (
            ("fund6", "F6", 10),
            ("fund9", "F9", 20),
            ("medio1", "M1", 30),
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
            self.alunos[nome] = usuario

        regra = XPRegra.objects.create(atividade="quiz", xp=10, ativa=True)
        for nome, pontos in (("fund6", 10), ("fund9", 20), ("medio1", 30)):
            regra.xp = pontos
            regra.save()
            conceder_xp(
                self.alunos[nome], "quiz", uuid.uuid4(), "Conclusão de quiz"
            )
        self.client.force_login(self.alunos["fund6"])

    def test_ranking_filtra_categorias_e_oferece_periodo_anual(self):
        resposta = self.client.get(
            reverse("ranking"), {"categoria": "fundamental", "periodo": "temporada"}
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            [linha["apelido_ranking"] for linha in resposta.context["ranking"]],
            ["Apelido-fund9", "Apelido-fund6"],
        )

        resposta = self.client.get(reverse("ranking"), {"categoria": "medio"})
        self.assertEqual(
            [linha["apelido_ranking"] for linha in resposta.context["ranking"]],
            ["Apelido-medio1"],
        )

        resposta = self.client.get(
            reverse("ranking"), {"categoria": "global", "periodo": "anual"}
        )
        self.assertEqual(resposta.context["periodo_tipo"], "anual")
        self.assertEqual(resposta.context["xp_pontuacao"], 10)
        self.assertEqual(
            [linha["apelido_ranking"] for linha in resposta.context["ranking"]],
            ["Apelido-medio1", "Apelido-fund9", "Apelido-fund6"],
        )

    def test_aluno_consulta_resultados_de_periodo_encerrado(self):
        periodo = XPPeriodo.objects.create(
            tipo=XPPeriodo.Tipo.ANUAL,
            chave="2025",
            inicio="2025-01-01",
            fim="2025-12-31",
            fechado=True,
        )
        ResultadoRanking.objects.create(
            periodo=periodo,
            categoria=ResultadoRanking.Categoria.GLOBAL,
            posicao=1,
            apelido="Campeão anônimo",
            xp=120,
        )

        resposta = self.client.get(reverse("resultados_ranking"))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Período anual 2025")
        self.assertContains(resposta, "Campeão anônimo")
        self.assertContains(resposta, "120 XP")
