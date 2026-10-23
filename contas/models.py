from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):
    class Papel(models.TextChoices):
        ALUNO = "aluno", "Aluno"
        PROFESSOR = "professor", "Professor"
        ADMIN = "admin", "Administrador"

    email = models.EmailField(unique=True)
    papel = models.CharField(
        max_length=10, choices=Papel.choices, default=Papel.ALUNO
    )


class PerfilAluno(models.Model):
    class Avatar(models.TextChoices):
        AURORA = "aurora", "Aurora"
        OCEANO = "oceano", "Oceano"
        FLORESTA = "floresta", "Floresta"
        AMETISTA = "ametista", "Ametista"

    class Serie(models.TextChoices):
        F6 = "F6", "6º ano (Fundamental)"
        F7 = "F7", "7º ano (Fundamental)"
        F8 = "F8", "8º ano (Fundamental)"
        F9 = "F9", "9º ano (Fundamental)"
        M1 = "M1", "1º ano (Médio)"
        M2 = "M2", "2º ano (Médio)"
        M3 = "M3", "3º ano (Médio)"

    usuario = models.OneToOneField(
        Usuario, on_delete=models.CASCADE, related_name="perfil_aluno"
    )
    serie = models.CharField(max_length=2, choices=Serie.choices)
    nome_exibicao = models.CharField(max_length=40, blank=True)
    apelido_ranking = models.CharField(max_length=24, blank=True)
    participar_ranking = models.BooleanField(default=False)
    avatar = models.CharField(
        max_length=10, choices=Avatar.choices, default=Avatar.AURORA
    )
    foto = models.ImageField(upload_to="avatars/%Y/%m/", blank=True)
    imagem_fundo = models.ImageField(upload_to="fundos-perfil/%Y/%m/", blank=True)
    foto_publica = models.BooleanField(default=False)
    escola_autorizou = models.BooleanField(default=False)
    escola_autorizou_em = models.DateTimeField(null=True, blank=True)
    versao_aviso = models.CharField(max_length=20, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("apelido_ranking",),
                condition=models.Q(participar_ranking=True),
                name="apelido_unico_no_ranking",
            )
        ]

    def __str__(self):
        return f"{self.usuario.username} ({self.get_serie_display()})"


class CodigoProfessor(models.Model):
    codigo_hash = models.CharField(max_length=128, editable=False)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey(
        Usuario, null=True, blank=True, on_delete=models.SET_NULL, editable=False
    )

    class Meta:
        verbose_name_plural = "códigos de professor"

    def definir_codigo(self, codigo):
        self.codigo_hash = make_password(codigo)

    def confere(self, codigo):
        return self.ativo and check_password(codigo, self.codigo_hash)

    def __str__(self):
        estado = "ativo" if self.ativo else "revogado"
        return f"Código criado em {self.criado_em:%d/%m/%Y} ({estado})"
