import uuid
from datetime import timedelta

from django.core.validators import MaxLengthValidator, MinValueValidator
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from contas.models import PerfilAluno


def arquivo_assunto_upload(instance, filename):
    return f"materiais/{uuid.uuid4().hex}.pdf"


def validar_arquivo_pdf(arquivo):
    if arquivo.size > 20 * 1024 * 1024:
        raise ValidationError("O arquivo PDF deve ter no máximo 20 MB.")
    if not arquivo.name.lower().endswith(".pdf"):
        raise ValidationError("Envie um arquivo com extensão PDF.")
    try:
        assinatura = arquivo.read(5)
        arquivo.seek(0)
    except (OSError, AttributeError) as exc:
        raise ValidationError("Não foi possível ler o arquivo enviado.") from exc
    if assinatura != b"%PDF-":
        raise ValidationError("O arquivo enviado não parece ser um PDF válido.")


class Materia(models.Model):
    nome = models.CharField(max_length=60, unique=True)
    descricao = models.CharField(max_length=200, blank=True)
    cor = models.CharField(
        max_length=7, default="#4f46e5", help_text="Cor em hexadecimal, ex.: #4f46e5"
    )
    destaque = models.BooleanField(default=True)
    ordem = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["ordem", "nome"]
        verbose_name_plural = "matérias"

    def __str__(self):
        return self.nome


class ConfiguracaoColagem(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    bloquear_colagem_professor = models.BooleanField(default=False)
    bloquear_colagem_admin = models.BooleanField(default=False)

    class Meta:
        verbose_name = "configuração de colagem"
        verbose_name_plural = "configuração de colagem"

    @property
    def bloqueio_ativo(self):
        return self.bloquear_colagem_professor or self.bloquear_colagem_admin

    def __str__(self):
        estado = "ativo" if self.bloqueio_ativo else "inativo"
        return f"Bloqueio de colagem {estado}"


class NotificacaoAluno(models.Model):
    class Tipo(models.TextChoices):
        MATERIAL = "material", "Novo material"
        QUIZ = "quiz", "Novo quiz"
        MATERIA = "materia", "Nova matéria"

    usuario = models.ForeignKey(
        "contas.Usuario", on_delete=models.CASCADE, related_name="notificacoes_estudo"
    )
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    titulo = models.CharField(max_length=160)
    mensagem = models.CharField(max_length=250)
    destino = models.CharField(max_length=300)
    criada_em = models.DateTimeField(auto_now_add=True)
    lida_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-criada_em"]
        indexes = [models.Index(fields=("usuario", "lida_em", "-criada_em"))]

    def __str__(self):
        return f"{self.get_tipo_display()} para {self.usuario}"


class Assunto(models.Model):
    class TipoMaterial(models.TextChoices):
        TEXTO = "texto", "Texto"
        RESUMO = "resumo", "Resumo"
        MAPA_MENTAL = "mapa_mental", "Mapa mental"
        EXERCICIOS = "exercicios", "Exercícios"

    class Dificuldade(models.TextChoices):
        INTRODUTORIA = "introdutoria", "Introdutória"
        INTERMEDIARIA = "intermediaria", "Intermediária"
        AVANCADA = "avancada", "Avançada"

    materia = models.ForeignKey(
        Materia, on_delete=models.CASCADE, related_name="assuntos"
    )
    serie = models.CharField(max_length=2, choices=PerfilAluno.Serie.choices)
    titulo = models.CharField(max_length=120)
    resumo = models.TextField(blank=True)
    conteudo_completo = models.TextField(
        blank=True,
        help_text="Texto exibido no leitor. Separe os parágrafos com uma linha em branco.",
    )
    arquivo = models.FileField(
        upload_to=arquivo_assunto_upload,
        blank=True,
        validators=(validar_arquivo_pdf,),
        help_text="PDF complementar opcional, com tamanho máximo de 20 MB.",
    )
    tipo_material = models.CharField(
        max_length=20, choices=TipoMaterial.choices, default=TipoMaterial.TEXTO
    )
    dificuldade = models.CharField(
        max_length=15,
        choices=Dificuldade.choices,
        default=Dificuldade.INTRODUTORIA,
    )
    objetivos_aprendizagem = models.TextField(blank=True)
    palavras_chave = models.CharField(max_length=250, blank=True)
    fonte_referencia = models.CharField(max_length=250, blank=True)
    ordem = models.PositiveIntegerField(default=0)
    publicado = models.BooleanField(default=True)
    publicar_em = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Opcional. Com 'Publicado' marcado, uma data futura agenda a publicação.",
    )
    notificacao_enviada_em = models.DateTimeField(null=True, blank=True, editable=False)
    autor = models.ForeignKey(
        "contas.Usuario",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assuntos_criados",
    )

    class Meta:
        ordering = ["ordem", "titulo"]
        verbose_name_plural = "assuntos"

    def __str__(self):
        return f"{self.materia} - {self.get_serie_display()} - {self.titulo}"


class EventoCalendario(models.Model):
    class Tipo(models.TextChoices):
        PROVA = "prova", "Prova"
        TRABALHO = "trabalho", "Trabalho"
        PRAZO = "prazo", "Prazo de entrega"
        OUTRO = "outro", "Outra atividade"

    materia = models.ForeignKey(Materia, on_delete=models.PROTECT, related_name="eventos")
    serie = models.CharField(max_length=2, choices=PerfilAluno.Serie.choices)
    titulo = models.CharField(max_length=120)
    descricao = models.TextField(blank=True, validators=[MaxLengthValidator(2000)])
    tipo = models.CharField(max_length=12, choices=Tipo.choices, default=Tipo.PRAZO)
    data = models.DateField()
    criado_por = models.ForeignKey(
        "contas.Usuario", on_delete=models.CASCADE, related_name="eventos_calendario"
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["data", "materia__nome", "titulo"]
        indexes = [models.Index(fields=("serie", "data"))]

    def __str__(self):
        return f"{self.get_tipo_display()}: {self.titulo} ({self.data:%d/%m/%Y})"


class ComentarioMaterial(models.Model):
    assunto = models.ForeignKey(Assunto, on_delete=models.CASCADE, related_name="comentarios")
    autor = models.ForeignKey(
        "contas.Usuario", on_delete=models.CASCADE, related_name="comentarios_materiais"
    )
    resposta_a = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="respostas",
    )
    texto = models.TextField(validators=[MaxLengthValidator(4000)])
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["criado_em"]
        indexes = [models.Index(fields=("assunto", "criado_em"))]

    def __str__(self):
        return f"Comentário de {self.autor} em {self.assunto}"


class PerguntaAluno(models.Model):
    class Status(models.TextChoices):
        PENDENTE = "pendente", "Aguardando moderação"
        APROVADA = "aprovada", "Publicada"
        REJEITADA = "rejeitada", "Não publicada"

    materia = models.ForeignKey(Materia, on_delete=models.PROTECT, related_name="perguntas")
    serie = models.CharField(max_length=2, choices=PerfilAluno.Serie.choices)
    titulo = models.CharField(max_length=120)
    texto = models.TextField(validators=[MaxLengthValidator(4000)])
    autor = models.ForeignKey(
        "contas.Usuario", on_delete=models.CASCADE, related_name="perguntas_estudo"
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDENTE
    )
    moderada_por = models.ForeignKey(
        "contas.Usuario",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="perguntas_moderadas",
    )
    criada_em = models.DateTimeField(auto_now_add=True)
    moderada_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-criada_em"]
        indexes = [models.Index(fields=("serie", "status", "-criada_em"))]

    def __str__(self):
        return self.titulo


class RespostaPergunta(models.Model):
    class Status(models.TextChoices):
        PENDENTE = "pendente", "Aguardando moderação"
        APROVADA = "aprovada", "Publicada"
        REJEITADA = "rejeitada", "Não publicada"

    pergunta = models.ForeignKey(
        PerguntaAluno, on_delete=models.CASCADE, related_name="respostas"
    )
    autor = models.ForeignKey(
        "contas.Usuario", on_delete=models.CASCADE, related_name="respostas_estudo"
    )
    texto = models.TextField(validators=[MaxLengthValidator(4000)])
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDENTE
    )
    moderada_por = models.ForeignKey(
        "contas.Usuario",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="respostas_moderadas",
    )
    criada_em = models.DateTimeField(auto_now_add=True)
    moderada_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["criada_em"]
        indexes = [models.Index(fields=("status", "criada_em"))]

    def __str__(self):
        return f"Resposta para {self.pergunta}"


class Marcacao(models.Model):
    class Cor(models.TextChoices):
        AMARELO = "amarelo", "Amarelo"
        AZUL = "azul", "Azul"
        VERDE = "verde", "Verde"
        ROSA = "rosa", "Rosa"
        LARANJA = "laranja", "Laranja"
        ROXO = "roxo", "Roxo"
        VERMELHO = "vermelho", "Vermelho"
        TURQUESA = "turquesa", "Turquesa"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(
        "contas.Usuario", on_delete=models.CASCADE, related_name="marcacoes_leitura"
    )
    assunto = models.ForeignKey(
        Assunto, on_delete=models.CASCADE, related_name="marcacoes"
    )
    trecho_id = models.CharField(max_length=40)
    trecho_texto = models.CharField(max_length=1000)
    cor = models.CharField(max_length=10, choices=Cor.choices, default=Cor.AMARELO)
    etiqueta = models.CharField(max_length=40, blank=True)
    anotacao = models.CharField(max_length=500, blank=True)
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criada_em"]

    def __str__(self):
        return f"Marcação de {self.usuario} em {self.assunto}"


class Quiz(models.Model):
    materia = models.ForeignKey(
        Materia, on_delete=models.PROTECT, related_name="quizzes"
    )
    titulo = models.CharField(max_length=120)
    descricao = models.TextField(blank=True)
    serie = models.CharField(
        max_length=2,
        choices=PerfilAluno.Serie.choices,
        blank=True,
        help_text="Deixe em branco para disponibilizar em todas as séries.",
    )
    publicado = models.BooleanField(default=False)
    publicar_em = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Opcional. Com 'Publicado' marcado, uma data futura agenda a publicação.",
    )
    notificacao_enviada_em = models.DateTimeField(null=True, blank=True, editable=False)
    criado_por = models.ForeignKey(
        "contas.Usuario",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="quizzes_criados",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["materia__nome", "titulo"]

    def __str__(self):
        return self.titulo


class QuizQuestao(models.Model):
    class AlternativaCorreta(models.TextChoices):
        A = "A", "Alternativa A"
        B = "B", "Alternativa B"
        C = "C", "Alternativa C"
        D = "D", "Alternativa D"

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questoes")
    enunciado = models.TextField()
    alternativa_a = models.CharField(max_length=250)
    alternativa_b = models.CharField(max_length=250)
    alternativa_c = models.CharField(max_length=250)
    alternativa_d = models.CharField(max_length=250)
    resposta_correta = models.CharField(
        max_length=1, choices=AlternativaCorreta.choices
    )
    explicacao = models.TextField(blank=True)
    ordem = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["ordem", "id"]

    def __str__(self):
        return f"{self.quiz}: {self.enunciado[:70]}"


class QuizTentativa(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(
        "contas.Usuario", on_delete=models.CASCADE, related_name="tentativas_quiz"
    )
    quiz = models.ForeignKey(
        Quiz, on_delete=models.PROTECT, related_name="tentativas"
    )
    token_envio = models.UUIDField()
    total_questoes = models.PositiveIntegerField()
    acertos = models.PositiveIntegerField()
    iniciada_em = models.DateTimeField(auto_now_add=True)
    finalizada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-finalizada_em"]
        constraints = [
            models.UniqueConstraint(
                fields=("usuario", "quiz", "token_envio"),
                name="quiz_tentativa_envio_unico",
            )
        ]

    @property
    def percentual(self):
        if not self.total_questoes:
            return 0
        return round(self.acertos * 100 / self.total_questoes)

    def __str__(self):
        return f"{self.usuario} - {self.quiz} ({self.acertos}/{self.total_questoes})"


class QuizResposta(models.Model):
    tentativa = models.ForeignKey(
        QuizTentativa, on_delete=models.CASCADE, related_name="respostas"
    )
    questao = models.ForeignKey(
        QuizQuestao, on_delete=models.PROTECT, related_name="respostas"
    )
    alternativa_escolhida = models.CharField(
        max_length=1, choices=QuizQuestao.AlternativaCorreta.choices
    )
    acertou = models.BooleanField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("tentativa", "questao"),
                name="quiz_resposta_por_questao_unica",
            )
        ]


class NotaAvaliacao(models.Model):
    class Tipo(models.TextChoices):
        PROVA = "prova", "Prova"
        TRABALHO = "trabalho", "Trabalho"
        ATIVIDADE = "atividade", "Atividade"
        PARTICIPACAO = "participacao", "Participação"
        OUTRO = "outro", "Outro"

    professor = models.ForeignKey(
        "contas.Usuario", on_delete=models.PROTECT, related_name="notas_lancadas"
    )
    aluno = models.ForeignKey(
        "contas.Usuario", on_delete=models.CASCADE, related_name="notas_avaliacoes"
    )
    materia = models.ForeignKey(
        Materia, on_delete=models.PROTECT, related_name="notas_avaliacoes"
    )
    titulo = models.CharField(max_length=120)
    tipo = models.CharField(max_length=15, choices=Tipo.choices, default=Tipo.OUTRO)
    nota = models.DecimalField(
        max_digits=6, decimal_places=2, validators=[MinValueValidator(0)]
    )
    nota_maxima = models.DecimalField(
        max_digits=6, decimal_places=2, default=10,
        validators=[MinValueValidator(0.01)],
    )
    data_avaliacao = models.DateField(default=timezone.localdate)
    observacoes = models.CharField(max_length=1000, blank=True)
    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data_avaliacao", "materia__nome", "titulo"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(nota__lte=models.F("nota_maxima")),
                name="nota_avaliacao_nao_excede_maximo",
            )
        ]
        indexes = [models.Index(fields=("aluno", "-data_avaliacao"))]

    def clean(self):
        super().clean()
        if self.aluno_id and self.aluno.papel != "aluno":
            raise ValidationError({"aluno": "Selecione uma conta de aluno."})
        if self.professor_id and self.professor.papel != "professor":
            raise ValidationError({"professor": "O responsável deve ser professor."})
        if self.nota is not None and self.nota_maxima is not None:
            if self.nota > self.nota_maxima:
                raise ValidationError({"nota": "A nota não pode superar a nota máxima."})

    def __str__(self):
        return f"{self.aluno} — {self.materia}: {self.nota}/{self.nota_maxima}"


def prazo_convite_desafio():
    return timezone.now() + timedelta(hours=48)


class DesafioPvP(models.Model):
    class Status(models.TextChoices):
        ABERTO = "aberto", "Aguardando adversário"
        EM_ANDAMENTO = "em_andamento", "Em andamento"
        CONCLUIDO = "concluido", "Concluído"
        EXPIRADO = "expirado", "Expirado"
        CANCELADO = "cancelado", "Cancelado"

    class Resultado(models.TextChoices):
        EMPATE = "empate", "Empate"
        CRIADOR = "criador", "Vitória do criador"
        CONVIDADO = "convidado", "Vitória do convidado"

    convite = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    criador = models.ForeignKey(
        "contas.Usuario", on_delete=models.CASCADE, related_name="desafios_criados"
    )
    convidado = models.ForeignKey(
        "contas.Usuario",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="desafios_aceitos",
    )
    quiz = models.ForeignKey(Quiz, on_delete=models.PROTECT, related_name="desafios")
    serie = models.CharField(max_length=2, choices=PerfilAluno.Serie.choices)
    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.ABERTO
    )
    resultado = models.CharField(
        max_length=10, choices=Resultado.choices, blank=True
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    expira_em = models.DateTimeField(default=prazo_convite_desafio)
    concluido_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [models.Index(fields=("status", "expira_em"))]

    def __str__(self):
        return f"Desafio {self.convite} ({self.get_status_display()})"


class DesafioQuestao(models.Model):
    desafio = models.ForeignKey(
        DesafioPvP, on_delete=models.CASCADE, related_name="questoes"
    )
    ordem = models.PositiveSmallIntegerField()
    enunciado = models.TextField()
    alternativa_a = models.CharField(max_length=250)
    alternativa_b = models.CharField(max_length=250)
    alternativa_c = models.CharField(max_length=250)
    alternativa_d = models.CharField(max_length=250)
    resposta_correta = models.CharField(
        max_length=1, choices=QuizQuestao.AlternativaCorreta.choices
    )

    class Meta:
        ordering = ["ordem"]
        constraints = [
            models.UniqueConstraint(
                fields=("desafio", "ordem"), name="desafio_questao_ordem_unica"
            )
        ]


class DesafioPartida(models.Model):
    desafio = models.ForeignKey(
        DesafioPvP, on_delete=models.CASCADE, related_name="partidas"
    )
    usuario = models.ForeignKey(
        "contas.Usuario", on_delete=models.CASCADE, related_name="partidas_pvp"
    )
    acertos = models.PositiveSmallIntegerField(default=0)
    iniciada_em = models.DateTimeField(auto_now_add=True)
    finalizada_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("desafio", "usuario"), name="desafio_partida_por_usuario_unica"
            )
        ]


class DesafioResposta(models.Model):
    partida = models.ForeignKey(
        DesafioPartida, on_delete=models.CASCADE, related_name="respostas"
    )
    questao = models.ForeignKey(
        DesafioQuestao, on_delete=models.PROTECT, related_name="respostas"
    )
    alternativa_escolhida = models.CharField(
        max_length=1, choices=QuizQuestao.AlternativaCorreta.choices
    )
    acertou = models.BooleanField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("partida", "questao"), name="desafio_resposta_unica"
            )
        ]


class XPPeriodo(models.Model):
    class Tipo(models.TextChoices):
        TEMPORADA = "temporada", "Temporada mensal"
        ANUAL = "anual", "Período anual"

    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    chave = models.CharField(max_length=7)
    inicio = models.DateField()
    fim = models.DateField()
    fechado = models.BooleanField(default=False)

    class Meta:
        ordering = ["-inicio"]
        constraints = [
            models.UniqueConstraint(
                fields=("tipo", "chave"), name="xp_periodo_tipo_chave_unico"
            )
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.chave}"


class ResultadoRanking(models.Model):
    class Categoria(models.TextChoices):
        FUNDAMENTAL = "fundamental", "Fundamental"
        MEDIO = "medio", "Médio"
        GLOBAL = "global", "Global"

    periodo = models.ForeignKey(
        XPPeriodo, on_delete=models.PROTECT, related_name="resultados_ranking"
    )
    categoria = models.CharField(max_length=12, choices=Categoria.choices)
    posicao = models.PositiveIntegerField()
    apelido = models.CharField(max_length=24)
    xp = models.PositiveIntegerField()

    class Meta:
        ordering = ["categoria", "posicao"]

    def __str__(self):
        return f"{self.periodo} · {self.get_categoria_display()} · {self.posicao}º"


class XPRegra(models.Model):
    class Atividade(models.TextChoices):
        QUIZ = "quiz", "Conclusão de quiz"

    atividade = models.CharField(max_length=30, choices=Atividade.choices, unique=True)
    xp = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    ativa = models.BooleanField(default=False)
    atualizada_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "regra de XP"
        verbose_name_plural = "regras de XP"

    def __str__(self):
        estado = "ativa" if self.ativa else "inativa"
        return f"{self.get_atividade_display()}: {self.xp} XP ({estado})"


class XPTransacao(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(
        "contas.Usuario", on_delete=models.PROTECT, related_name="transacoes_xp"
    )
    regra = models.ForeignKey(
        XPRegra, null=True, blank=True, on_delete=models.PROTECT
    )
    missao = models.ForeignKey(
        "Missao",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="transacoes_xp",
    )
    origem = models.CharField(max_length=30)
    referencia = models.CharField(max_length=100)
    atividade = models.CharField(max_length=160)
    xp = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    temporada = models.ForeignKey(
        XPPeriodo,
        on_delete=models.PROTECT,
        related_name="transacoes_temporada",
    )
    periodo_anual = models.ForeignKey(
        XPPeriodo,
        on_delete=models.PROTECT,
        related_name="transacoes_anuais",
    )
    validada = models.BooleanField(default=True)
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criada_em"]
        constraints = [
            models.UniqueConstraint(
                fields=("usuario", "origem", "referencia"),
                name="xp_transacao_evento_unico",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(regra__isnull=False, missao__isnull=True)
                    | models.Q(regra__isnull=True, missao__isnull=False)
                ),
                name="xp_transacao_regra_ou_missao",
            ),
        ]

    def __str__(self):
        return f"{self.usuario}: +{self.xp} XP ({self.atividade})"


class Patente(models.Model):
    nome = models.CharField(max_length=60, unique=True)
    descricao = models.CharField(max_length=180, blank=True)
    xp_minimo = models.PositiveIntegerField(
        unique=True,
        validators=[MinValueValidator(0)],
        help_text="XP vitalício necessário para alcançar esta patente.",
    )
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ["xp_minimo", "nome"]
        verbose_name = "patente"
        verbose_name_plural = "patentes"

    def __str__(self):
        return f"{self.nome} ({self.xp_minimo} XP)"


class Titulo(models.Model):
    nome = models.CharField(max_length=60, unique=True)
    descricao = models.CharField(max_length=180, blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class TituloConcedido(models.Model):
    usuario = models.ForeignKey(
        "contas.Usuario", on_delete=models.CASCADE, related_name="titulos_concedidos"
    )
    titulo = models.ForeignKey(
        Titulo, on_delete=models.PROTECT, related_name="concessoes"
    )
    concedido_em = models.DateTimeField(auto_now_add=True)
    ativo = models.BooleanField(default=False)

    class Meta:
        ordering = ["-concedido_em"]
        constraints = [
            models.UniqueConstraint(
                fields=("usuario", "titulo"), name="titulo_unico_por_usuario"
            ),
            models.UniqueConstraint(
                fields=("usuario",),
                condition=models.Q(ativo=True),
                name="um_titulo_ativo_por_usuario",
            ),
        ]
        verbose_name = "título concedido"
        verbose_name_plural = "títulos concedidos"

    def __str__(self):
        return f"{self.usuario}: {self.titulo}"


class Conquista(models.Model):
    class Criterio(models.TextChoices):
        QUIZZES_CONCLUIDOS = "quizzes_concluidos", "Quizzes concluídos"
        QUIZZES_PERFEITOS = "quizzes_perfeitos", "Quizzes com 100% de acerto"
        XP_VITALICIO = "xp_vitalicio", "XP vitalício"

    nome = models.CharField(max_length=70, unique=True)
    descricao = models.CharField(max_length=200, blank=True)
    criterio = models.CharField(max_length=24, choices=Criterio.choices)
    meta = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ["criterio", "meta", "nome"]

    def __str__(self):
        return self.nome


class ConquistaConcedida(models.Model):
    usuario = models.ForeignKey(
        "contas.Usuario", on_delete=models.CASCADE, related_name="conquistas"
    )
    conquista = models.ForeignKey(
        Conquista, on_delete=models.PROTECT, related_name="concedidas"
    )
    conquistada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-conquistada_em"]
        constraints = [
            models.UniqueConstraint(
                fields=("usuario", "conquista"),
                name="conquista_unica_por_usuario",
            )
        ]

    def __str__(self):
        return f"{self.usuario}: {self.conquista}"


class Missao(models.Model):
    class Criterio(models.TextChoices):
        QUIZZES_CONCLUIDOS = "quizzes_concluidos", "Concluir quizzes"
        QUIZZES_PERFEITOS = "quizzes_perfeitos", "Acertar 100% dos quizzes"

    nome = models.CharField(max_length=100, unique=True)
    descricao = models.TextField(blank=True)
    criterio = models.CharField(max_length=24, choices=Criterio.choices)
    meta = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    recompensa_xp = models.PositiveIntegerField(default=0)
    inicio = models.DateTimeField(null=True, blank=True)
    fim = models.DateTimeField(null=True, blank=True)
    secreta = models.BooleanField(default=False)
    ativa = models.BooleanField(default=False)
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["inicio", "nome"]
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(fim__isnull=True) | models.Q(inicio__isnull=True) | models.Q(fim__gt=models.F("inicio"))),
                name="missao_fim_depois_inicio",
            )
        ]

    def __str__(self):
        return self.nome


class MissaoAluno(models.Model):
    usuario = models.ForeignKey(
        "contas.Usuario", on_delete=models.CASCADE, related_name="missoes"
    )
    missao = models.ForeignKey(
        Missao, on_delete=models.PROTECT, related_name="participacoes"
    )
    progresso = models.PositiveIntegerField(default=0)
    iniciada_em = models.DateTimeField(auto_now_add=True)
    concluida_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-iniciada_em"]
        constraints = [
            models.UniqueConstraint(
                fields=("usuario", "missao"), name="missao_unica_por_aluno"
            )
        ]

    def __str__(self):
        return f"{self.usuario}: {self.missao}"
