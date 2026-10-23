from io import BytesIO

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.files.uploadedfile import SimpleUploadedFile, UploadedFile
from django.utils import timezone
from PIL import Image, ImageOps

from conteudo.models import TituloConcedido

from .models import CodigoProfessor, PerfilAluno, Usuario

VERSAO_AVISO = "v1"


class CadastroAlunoForm(UserCreationForm):
    serie = forms.ChoiceField(choices=PerfilAluno.Serie.choices, label="Série")
    escola_autorizou = forms.BooleanField(
        required=True,
        label="A escola é responsável pelo meu cadastro e autorizou a minha inscrição.",
    )

    class Meta:
        model = Usuario
        fields = ("username", "email")

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.papel = Usuario.Papel.ALUNO
        if commit:
            usuario.save()
            PerfilAluno.objects.create(
                usuario=usuario,
                serie=self.cleaned_data["serie"],
                escola_autorizou=True,
                escola_autorizou_em=timezone.now(),
                versao_aviso=VERSAO_AVISO,
            )
        return usuario


class CadastroProfessorForm(UserCreationForm):
    codigo_professor = forms.CharField(
        label="Código de professor", widget=forms.PasswordInput
    )

    class Meta:
        model = Usuario
        fields = ("username", "email")

    def clean_codigo_professor(self):
        codigo = self.cleaned_data["codigo_professor"]
        codigos = CodigoProfessor.objects.filter(ativo=True)
        if not any(c.confere(codigo) for c in codigos):
            raise forms.ValidationError("Código inválido.")
        return codigo

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.papel = Usuario.Papel.PROFESSOR
        if commit:
            usuario.save()
        return usuario


class PerfilAlunoForm(forms.ModelForm):
    MAX_FOTO_BYTES = 5 * 1024 * 1024
    MAX_FOTO_LADO = 4096
    remover_foto = forms.BooleanField(
        required=False, label="Remover foto atual"
    )
    remover_imagem_fundo = forms.BooleanField(
        required=False, label="Remover imagem de fundo atual"
    )
    titulo_ativo = forms.ModelChoiceField(
        queryset=TituloConcedido.objects.none(),
        required=False,
        label="Título exibido no perfil",
        help_text="Você pode escolher apenas entre os títulos que recebeu.",
        empty_label="Sem título ativo",
    )

    def __init__(self, *args, **kwargs):
        self.usuario = kwargs.pop("usuario", None)
        super().__init__(*args, **kwargs)
        if self.usuario:
            self.fields["titulo_ativo"].queryset = (
                TituloConcedido.objects.filter(
                    usuario=self.usuario, titulo__ativo=True
                ).select_related("titulo")
            )
            atual = self.fields["titulo_ativo"].queryset.filter(ativo=True).first()
            self.initial["titulo_ativo"] = atual

    def salvar_titulo_ativo(self):
        if not self.usuario:
            return
        from django.db import transaction

        with transaction.atomic():
            TituloConcedido.objects.filter(usuario=self.usuario, ativo=True).update(
                ativo=False
            )
            selecionado = self.cleaned_data.get("titulo_ativo")
            if selecionado:
                TituloConcedido.objects.filter(
                    pk=selecionado.pk, usuario=self.usuario
                ).update(ativo=True)

    class Meta:
        model = PerfilAluno
        fields = (
            "nome_exibicao",
            "avatar",
            "foto",
            "imagem_fundo",
            "foto_publica",
            "participar_ranking",
            "apelido_ranking",
        )
        labels = {
            "nome_exibicao": "Nome de exibição",
            "participar_ranking": "Participar dos rankings",
            "apelido_ranking": "Apelido público no ranking",
            "avatar": "Escolha seu avatar",
            "foto": "Ou envie uma foto (JPEG ou PNG, até 5 MB)",
            "imagem_fundo": "Imagem de fundo da página inicial (JPEG ou PNG, até 5 MB)",
            "foto_publica": "Permitir que outros usuários vejam minha foto",
        }
        help_texts = {
            "imagem_fundo": "A imagem será exibida somente para você na página inicial.",
            "foto_publica": "Se marcada, a foto poderá ser vista por usuários conectados ao StudyVerse.",
            "participar_ranking": "A participação é opcional, começa desativada e pode ser desligada a qualquer momento.",
            "apelido_ranking": "Use um apelido; ele será mostrado aos outros participantes no ranking.",
        }
        widgets = {
            "avatar": forms.RadioSelect,
            "foto": forms.FileInput(attrs={"accept": "image/jpeg,image/png"}),
            "imagem_fundo": forms.FileInput(attrs={"accept": "image/jpeg,image/png"}),
        }

    def clean(self):
        dados = super().clean()
        apelido = (dados.get("apelido_ranking") or "").strip()
        participando = dados.get("participar_ranking", False)
        if participando and not apelido:
            self.add_error(
                "apelido_ranking", "Escolha um apelido para participar do ranking."
            )
        elif participando and self.usuario:
            duplicado = PerfilAluno.objects.filter(
                participar_ranking=True, apelido_ranking__iexact=apelido
            ).exclude(pk=self.instance.pk)
            if duplicado.exists():
                self.add_error(
                    "apelido_ranking", "Esse apelido já está em uso no ranking."
                )
        dados["apelido_ranking"] = apelido
        if dados.get("remover_foto") and not self.files.get("foto"):
            dados["foto"] = False
        if dados.get("remover_imagem_fundo") and not self.files.get("imagem_fundo"):
            dados["imagem_fundo"] = False
        return dados

    def clean_foto(self):
        foto = self.cleaned_data.get("foto")
        if not isinstance(foto, UploadedFile):
            return foto
        if foto.size > self.MAX_FOTO_BYTES:
            raise forms.ValidationError("A imagem deve ter no máximo 5 MB.")

        try:
            foto.seek(0)
            with Image.open(foto) as original:
                formato = original.format
                largura, altura = original.size
                if formato not in {"JPEG", "PNG"}:
                    raise forms.ValidationError(
                        "Envie uma imagem JPEG ou PNG válida."
                    )
                if largura > self.MAX_FOTO_LADO or altura > self.MAX_FOTO_LADO:
                    raise forms.ValidationError(
                        "A imagem não pode exceder 4096 × 4096 pixels."
                    )
                imagem = ImageOps.exif_transpose(original)
                imagem.thumbnail((512, 512))
        except (OSError, Image.DecompressionBombError) as exc:
            raise forms.ValidationError("Não foi possível ler essa imagem.") from exc
        finally:
            foto.seek(0)

        buffer = BytesIO()
        if formato == "JPEG":
            if imagem.mode not in {"RGB", "L"}:
                imagem = imagem.convert("RGB")
            imagem.save(buffer, format="JPEG", quality=88, optimize=True)
            nome, content_type = "foto-perfil.jpg", "image/jpeg"
        else:
            imagem = imagem.convert("RGBA")
            imagem.save(buffer, format="PNG", optimize=True)
            nome, content_type = "foto-perfil.png", "image/png"

        return SimpleUploadedFile(nome, buffer.getvalue(), content_type=content_type)

    def clean_imagem_fundo(self):
        imagem_fundo = self.cleaned_data.get("imagem_fundo")
        if not isinstance(imagem_fundo, UploadedFile):
            return imagem_fundo
        if imagem_fundo.size > self.MAX_FOTO_BYTES:
            raise forms.ValidationError("A imagem deve ter no máximo 5 MB.")

        try:
            imagem_fundo.seek(0)
            with Image.open(imagem_fundo) as original:
                formato = original.format
                largura, altura = original.size
                if formato not in {"JPEG", "PNG"}:
                    raise forms.ValidationError(
                        "Envie uma imagem JPEG ou PNG válida."
                    )
                if largura > self.MAX_FOTO_LADO or altura > self.MAX_FOTO_LADO:
                    raise forms.ValidationError(
                        "A imagem não pode exceder 4096 × 4096 pixels."
                    )
                imagem = ImageOps.exif_transpose(original)
                imagem.thumbnail((1920, 1080))
        except (OSError, Image.DecompressionBombError) as exc:
            raise forms.ValidationError("Não foi possível ler essa imagem.") from exc
        finally:
            imagem_fundo.seek(0)

        buffer = BytesIO()
        if formato == "JPEG":
            if imagem.mode not in {"RGB", "L"}:
                imagem = imagem.convert("RGB")
            imagem.save(buffer, format="JPEG", quality=88, optimize=True)
            nome, content_type = "fundo-perfil.jpg", "image/jpeg"
        else:
            imagem = imagem.convert("RGBA")
            imagem.save(buffer, format="PNG", optimize=True)
            nome, content_type = "fundo-perfil.png", "image/png"

        return SimpleUploadedFile(nome, buffer.getvalue(), content_type=content_type)
