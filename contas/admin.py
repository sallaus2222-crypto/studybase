from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import CodigoProfessor, PerfilAluno, Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("StudyVerse", {"fields": ("papel",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("StudyVerse", {"fields": ("email", "papel")}),
    )
    list_display = ("username", "email", "papel", "is_staff")
    list_filter = ("papel", "is_staff")


@admin.register(PerfilAluno)
class PerfilAlunoAdmin(admin.ModelAdmin):
    exclude = ("foto",)
    list_display = ("usuario", "serie", "participar_ranking", "apelido_ranking")
    list_filter = ("serie", "participar_ranking")
    search_fields = ("usuario__username", "apelido_ranking")


class CodigoProfessorForm(forms.ModelForm):
    codigo = forms.CharField(
        label="Código secreto",
        required=False,
        help_text="Preencha ao criar ou trocar o código. Ele nunca é guardado em texto, só o hash.",
    )

    class Meta:
        model = CodigoProfessor
        fields = ("ativo",)

    def clean(self):
        dados = super().clean()
        if not self.instance.pk and not dados.get("codigo"):
            raise forms.ValidationError("Informe o código secreto.")
        return dados


@admin.register(CodigoProfessor)
class CodigoProfessorAdmin(admin.ModelAdmin):
    form = CodigoProfessorForm
    fields = ("codigo", "ativo")
    list_display = ("__str__", "ativo", "criado_por")

    def save_model(self, request, obj, form, change):
        codigo = form.cleaned_data.get("codigo")
        if codigo:
            obj.definir_codigo(codigo)
        if not change:
            obj.criado_por = request.user
        super().save_model(request, obj, form, change)
