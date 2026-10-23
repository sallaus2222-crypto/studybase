from django import forms
from django.db.models import Count, Q
from django.forms import inlineformset_factory
from django.utils import timezone
from contas.models import Usuario

from .models import (
    Assunto,
    ComentarioMaterial,
    ConfiguracaoColagem,
    EventoCalendario,
    Marcacao,
    Materia,
    NotaAvaliacao,
    PerguntaAluno,
    RespostaPergunta,
    Quiz,
    QuizQuestao,
)


class DesafioPvPForm(forms.Form):
    quiz = forms.ModelChoiceField(
        queryset=Quiz.objects.none(),
        label="Quiz do desafio",
        empty_label="Escolha um quiz com dez questões",
    )

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        perfil = getattr(usuario, "perfil_aluno", None) if usuario else None
        if perfil:
            self.fields["quiz"].queryset = (
                Quiz.objects.filter(publicado=True)
                .filter(Q(publicar_em__isnull=True) | Q(publicar_em__lte=timezone.now()))
                .filter(Q(serie="") | Q(serie=perfil.serie))
                .annotate(total_questoes=Count("questoes", distinct=True))
                .filter(total_questoes__gte=10)
                .select_related("materia")
                .order_by("materia__nome", "titulo")
            )


class AssuntoForm(forms.ModelForm):
    class Meta:
        model = Assunto
        fields = (
            "materia",
            "serie",
            "titulo",
            "conteudo_completo",
            "arquivo",
            "tipo_material",
            "dificuldade",
            "resumo",
            "objetivos_aprendizagem",
            "palavras_chave",
            "fonte_referencia",
            "ordem",
            "publicar_em",
            "publicado",
        )
        labels = {
            "publicar_em": "Data e hora da publicação (opcional)",
            "publicado": "Publicar este material",
        }
        widgets = {
            "resumo": forms.Textarea(attrs={"rows": 6}),
            "conteudo_completo": forms.Textarea(attrs={"rows": 14}),
            "objetivos_aprendizagem": forms.Textarea(attrs={"rows": 4}),
            "publicar_em": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }


class EventoCalendarioForm(forms.ModelForm):
    class Meta:
        model = EventoCalendario
        fields = ("materia", "serie", "titulo", "tipo", "data", "descricao")
        widgets = {
            "data": forms.DateInput(attrs={"type": "date"}),
            "descricao": forms.Textarea(attrs={"rows": 4, "maxlength": 2000}),
        }


class ComentarioMaterialForm(forms.ModelForm):
    class Meta:
        model = ComentarioMaterial
        fields = ("texto",)
        labels = {"texto": "Dúvida ou comentário"}
        widgets = {
            "texto": forms.Textarea(
                attrs={"rows": 4, "maxlength": 4000, "placeholder": "Escreva sua dúvida ou resposta..."}
            )
        }


class MateriaForm(forms.ModelForm):
    class Meta:
        model = Materia
        fields = ("nome", "descricao", "cor", "destaque", "ordem")
        widgets = {
            "descricao": forms.Textarea(attrs={"rows": 3, "maxlength": 200}),
            "cor": forms.TextInput(attrs={"type": "color"}),
        }


class BloqueioColagemProfessorForm(forms.ModelForm):
    class Meta:
        model = ConfiguracaoColagem
        fields = ("bloquear_colagem_professor",)
        labels = {"bloquear_colagem_professor": "Bloquear colar nos campos de texto dos alunos"}


class BloqueioColagemAdminForm(forms.ModelForm):
    class Meta:
        model = ConfiguracaoColagem
        fields = ("bloquear_colagem_admin",)
        labels = {"bloquear_colagem_admin": "Bloquear colar nos campos de texto dos alunos"}

class MarcacaoForm(forms.ModelForm):
    class Meta:
        model = Marcacao
        fields = ("trecho_id", "trecho_texto", "cor", "etiqueta", "anotacao")
        widgets = {
            "trecho_id": forms.HiddenInput(),
            "trecho_texto": forms.HiddenInput(),
            "anotacao": forms.Textarea(attrs={"rows": 3}),
        }


class PerguntaAlunoForm(forms.ModelForm):
    class Meta:
        model = PerguntaAluno
        fields = ("materia", "titulo", "texto")
        widgets = {
            "titulo": forms.TextInput(attrs={"maxlength": 120}),
            "texto": forms.Textarea(attrs={"rows": 5, "maxlength": 4000}),
        }


class RespostaPerguntaForm(forms.ModelForm):
    class Meta:
        model = RespostaPergunta
        fields = ("texto",)
        widgets = {"texto": forms.Textarea(attrs={"rows": 4, "maxlength": 4000})}


class NotaAvaliacaoForm(forms.ModelForm):
    class Meta:
        model = NotaAvaliacao
        fields = (
            "aluno",
            "materia",
            "titulo",
            "tipo",
            "nota",
            "nota_maxima",
            "data_avaliacao",
            "observacoes",
        )
        widgets = {
            "data_avaliacao": forms.DateInput(attrs={"type": "date"}),
            "observacoes": forms.Textarea(attrs={"rows": 3, "maxlength": 1000}),
            "nota": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "nota_maxima": forms.NumberInput(attrs={"min": "0.01", "step": "0.01"}),
        }

    def __init__(self, *args, professor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["aluno"].queryset = (
            Usuario.objects.filter(papel=Usuario.Papel.ALUNO, perfil_aluno__isnull=False)
            .select_related("perfil_aluno")
            .order_by("perfil_aluno__serie", "username")
        )
        self.fields["aluno"].label_from_instance = lambda aluno: (
            f"{aluno.perfil_aluno.get_serie_display()} · "
            f"{aluno.perfil_aluno.nome_exibicao or aluno.username}"
        )
        self.fields["materia"].queryset = Materia.objects.order_by("nome")
        self.fields["observacoes"].required = False
        self.professor = professor


class QuizForm(forms.ModelForm):
    class Meta:
        model = Quiz
        fields = ("materia", "titulo", "descricao", "serie", "publicar_em", "publicado")
        labels = {
            "publicar_em": "Data e hora da publicação (opcional)",
            "publicado": "Publicar este quiz",
        }
        widgets = {
            "descricao": forms.Textarea(attrs={"rows": 3}),
            "publicar_em": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }


class QuizQuestaoForm(forms.ModelForm):
    class Meta:
        model = QuizQuestao
        fields = (
            "enunciado",
            "alternativa_a",
            "alternativa_b",
            "alternativa_c",
            "alternativa_d",
            "resposta_correta",
            "explicacao",
            "ordem",
        )
        widgets = {
            "enunciado": forms.Textarea(attrs={"rows": 3}),
            "explicacao": forms.Textarea(attrs={"rows": 2}),
        }


QuizQuestaoFormSet = inlineformset_factory(
    Quiz,
    QuizQuestao,
    form=QuizQuestaoForm,
    extra=1,
    min_num=1,
    validate_min=True,
    can_delete=True,
)
