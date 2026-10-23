from django.contrib import admin

from .models import (
    Assunto,
    DesafioPartida,
    DesafioPvP,
    DesafioQuestao,
    DesafioResposta,
    Conquista,
    ConquistaConcedida,
    ConfiguracaoColagem,
    Marcacao,
    NotaAvaliacao,
    Materia,
    Missao,
    MissaoAluno,
    PerguntaAluno,
    Patente,
    Quiz,
    QuizQuestao,
    QuizResposta,
    QuizTentativa,
    ResultadoRanking,
    RespostaPergunta,
    Titulo,
    TituloConcedido,
    XPPeriodo,
    XPRegra,
    XPTransacao,
)
from .services import fechar_periodo_ranking


@admin.register(NotaAvaliacao)
class NotaAvaliacaoAdmin(admin.ModelAdmin):
    list_display = ("aluno", "materia", "titulo", "nota", "nota_maxima", "data_avaliacao", "professor")
    list_filter = ("tipo", "materia", "data_avaliacao")
    search_fields = ("aluno__username", "aluno__perfil_aluno__nome_exibicao", "titulo")


@admin.register(ConfiguracaoColagem)
class ConfiguracaoColagemAdmin(admin.ModelAdmin):
    list_display = ("id", "bloquear_colagem_professor", "bloquear_colagem_admin", "bloqueio_ativo")
    fields = ("bloquear_colagem_professor", "bloquear_colagem_admin")

    def has_add_permission(self, request):
        return not ConfiguracaoColagem.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DesafioPvP)
class DesafioPvPAdmin(admin.ModelAdmin):
    list_display = ("convite", "quiz", "serie", "status", "criado_em", "expira_em")
    list_filter = ("status", "serie", "quiz__materia")
    search_fields = ("convite", "criador__username", "convidado__username")
    readonly_fields = (
        "convite", "criador", "convidado", "quiz", "serie", "status",
        "resultado", "criado_em", "expira_em", "concluido_em",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DesafioQuestao)
class DesafioQuestaoAdmin(admin.ModelAdmin):
    list_display = ("desafio", "ordem", "enunciado")
    readonly_fields = (
        "desafio", "ordem", "enunciado", "alternativa_a", "alternativa_b",
        "alternativa_c", "alternativa_d", "resposta_correta",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DesafioPartida)
class DesafioPartidaAdmin(admin.ModelAdmin):
    list_display = ("desafio", "usuario", "acertos", "iniciada_em", "finalizada_em")
    list_filter = ("finalizada_em",)
    search_fields = ("usuario__username", "desafio__convite")
    readonly_fields = ("desafio", "usuario", "acertos", "iniciada_em", "finalizada_em")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DesafioResposta)
class DesafioRespostaAdmin(admin.ModelAdmin):
    list_display = ("partida", "questao", "alternativa_escolhida", "acertou")
    list_filter = ("acertou",)
    readonly_fields = ("partida", "questao", "alternativa_escolhida", "acertou")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Missao)
class MissaoAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "criterio",
        "meta",
        "recompensa_xp",
        "inicio",
        "fim",
        "ativa",
        "secreta",
    )
    list_filter = ("criterio", "ativa", "secreta")
    search_fields = ("nome", "descricao")


@admin.register(MissaoAluno)
class MissaoAlunoAdmin(admin.ModelAdmin):
    list_display = ("usuario", "missao", "progresso", "concluida_em")
    list_filter = ("missao", "concluida_em")
    search_fields = ("usuario__username", "missao__nome")
    readonly_fields = ("usuario", "missao", "progresso", "iniciada_em", "concluida_em")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PerguntaAluno)
class PerguntaAlunoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "materia", "serie", "autor", "status", "criada_em")
    list_filter = ("status", "serie", "materia")
    search_fields = ("titulo", "texto", "autor__username")
    readonly_fields = (
        "materia", "serie", "titulo", "texto", "autor", "status",
        "moderada_por", "criada_em", "moderada_em",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RespostaPergunta)
class RespostaPerguntaAdmin(admin.ModelAdmin):
    list_display = ("pergunta", "autor", "status", "criada_em")
    list_filter = ("status", "pergunta__serie", "pergunta__materia")
    search_fields = ("texto", "autor__username", "pergunta__titulo")
    readonly_fields = (
        "pergunta", "autor", "texto", "status", "moderada_por",
        "criada_em", "moderada_em",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Conquista)
class ConquistaAdmin(admin.ModelAdmin):
    list_display = ("nome", "criterio", "meta", "ativa")
    list_filter = ("criterio", "ativa")
    list_editable = ("ativa",)
    search_fields = ("nome", "descricao")


@admin.register(ConquistaConcedida)
class ConquistaConcedidaAdmin(admin.ModelAdmin):
    list_display = ("usuario", "conquista", "conquistada_em")
    list_filter = ("conquista", "conquistada_em")
    search_fields = ("usuario__username", "conquista__nome")
    readonly_fields = ("usuario", "conquista", "conquistada_em")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Patente)
class PatenteAdmin(admin.ModelAdmin):
    list_display = ("nome", "xp_minimo", "ativa")
    list_editable = ("xp_minimo", "ativa")
    search_fields = ("nome", "descricao")
    ordering = ("xp_minimo",)


@admin.register(Titulo)
class TituloAdmin(admin.ModelAdmin):
    list_display = ("nome", "ativo")
    list_editable = ("ativo",)
    search_fields = ("nome", "descricao")


@admin.register(TituloConcedido)
class TituloConcedidoAdmin(admin.ModelAdmin):
    list_display = ("usuario", "titulo", "ativo", "concedido_em")
    list_filter = ("titulo", "ativo", "concedido_em")
    search_fields = ("usuario__username", "usuario__email", "titulo__nome")
    readonly_fields = ("concedido_em",)


@admin.register(Materia)
class MateriaAdmin(admin.ModelAdmin):
    list_display = ("nome", "cor", "destaque", "ordem")
    list_editable = ("destaque", "ordem")


@admin.register(Assunto)
class AssuntoAdmin(admin.ModelAdmin):
    list_display = (
        "titulo",
        "materia",
        "serie",
        "tipo_material",
        "dificuldade",
        "ordem",
        "publicado",
    )
    list_filter = ("materia", "serie", "tipo_material", "dificuldade", "publicado")


@admin.register(Marcacao)
class MarcacaoAdmin(admin.ModelAdmin):
    list_display = ("usuario", "assunto", "cor", "etiqueta", "criada_em")
    list_filter = ("cor", "criada_em")
    search_fields = ("usuario__username", "assunto__titulo", "trecho_texto", "etiqueta")
    readonly_fields = ("id", "usuario", "assunto", "trecho_id", "trecho_texto", "criada_em")


class QuizQuestaoInline(admin.TabularInline):
    model = QuizQuestao
    extra = 1
    fields = (
        "ordem",
        "enunciado",
        "alternativa_a",
        "alternativa_b",
        "alternativa_c",
        "alternativa_d",
        "resposta_correta",
        "explicacao",
    )


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("titulo", "materia", "serie", "publicado", "criado_em")
    list_filter = ("materia", "serie", "publicado")
    search_fields = ("titulo", "descricao")
    list_editable = ("publicado",)
    inlines = (QuizQuestaoInline,)


@admin.register(QuizTentativa)
class QuizTentativaAdmin(admin.ModelAdmin):
    list_display = ("usuario", "quiz", "acertos", "total_questoes", "finalizada_em")
    list_filter = ("quiz", "finalizada_em")
    search_fields = ("usuario__username", "quiz__titulo")
    readonly_fields = (
        "id",
        "usuario",
        "quiz",
        "token_envio",
        "total_questoes",
        "acertos",
        "iniciada_em",
        "finalizada_em",
    )
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(QuizResposta)
class QuizRespostaAdmin(admin.ModelAdmin):
    list_display = ("tentativa", "questao", "alternativa_escolhida", "acertou")
    list_filter = ("acertou",)
    readonly_fields = ("tentativa", "questao", "alternativa_escolhida", "acertou")
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(XPRegra)
class XPRegraAdmin(admin.ModelAdmin):
    list_display = ("atividade", "xp", "ativa", "atualizada_em")
    list_editable = ("xp", "ativa")


@admin.register(XPPeriodo)
class XPPeriodoAdmin(admin.ModelAdmin):
    list_display = ("tipo", "chave", "inicio", "fim", "fechado")
    list_filter = ("tipo", "fechado")
    readonly_fields = ("tipo", "chave", "inicio", "fim", "fechado")
    actions = ("fechar_periodos_selecionados",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Fechar períodos concluídos e registrar rankings")
    def fechar_periodos_selecionados(self, request, queryset):
        fechados = 0
        erros = []
        for periodo in queryset:
            try:
                fechar_periodo_ranking(periodo)
                fechados += 1
            except ValueError as exc:
                erros.append(f"{periodo}: {exc}")
        if fechados:
            self.message_user(request, f"Resultados registrados em {fechados} período(s).")
        if erros:
            self.message_user(request, " ".join(erros), level="WARNING")


@admin.register(ResultadoRanking)
class ResultadoRankingAdmin(admin.ModelAdmin):
    list_display = ("periodo", "categoria", "posicao", "apelido", "xp")
    list_filter = ("periodo__tipo", "categoria", "periodo")
    search_fields = ("apelido", "periodo__chave")
    readonly_fields = ("periodo", "categoria", "posicao", "apelido", "xp")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(XPTransacao)
class XPTransacaoAdmin(admin.ModelAdmin):
    list_display = (
        "usuario",
        "origem",
        "atividade",
        "xp",
        "temporada",
        "periodo_anual",
        "validada",
        "criada_em",
    )
    list_filter = ("origem", "validada", "temporada", "periodo_anual")
    search_fields = ("usuario__username", "referencia", "atividade")
    readonly_fields = (
        "id",
        "usuario",
        "regra",
        "missao",
        "origem",
        "referencia",
        "atividade",
        "xp",
        "temporada",
        "periodo_anual",
        "validada",
        "criada_em",
    )
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
