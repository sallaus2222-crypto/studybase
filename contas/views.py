import os

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.db.models import IntegerField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET

from conteudo.models import Materia, ResultadoRanking, TituloConcedido, XPTransacao
from conteudo.services import progresso_patente, resumo_missoes, resumo_xp

from .forms import CadastroAlunoForm, CadastroProfessorForm, PerfilAlunoForm
from .models import PerfilAluno, Usuario


def cadastro_aluno(request):
    if request.method == "POST":
        form = CadastroAlunoForm(request.POST)
        if form.is_valid():
            usuario = form.save()
            login(request, usuario)
            return redirect("inicio")
    else:
        form = CadastroAlunoForm()
    return render(request, "contas/cadastro_aluno.html", {"form": form})


def cadastro_professor(request):
    if request.method == "POST":
        form = CadastroProfessorForm(request.POST)
        if form.is_valid():
            usuario = form.save()
            login(request, usuario)
            return redirect("inicio")
    else:
        form = CadastroProfessorForm()
    return render(request, "contas/cadastro_professor.html", {"form": form})


@login_required
def inicio(request):
    materias_destaque = Materia.objects.filter(destaque=True)[:4]
    contexto = {"materias_destaque": materias_destaque}
    if request.user.papel == Usuario.Papel.ALUNO:
        contexto["progresso_xp"] = resumo_xp(request.user)
        contexto["progresso_patente"] = progresso_patente(
            contexto["progresso_xp"]["xp_vitalicio"]
        )
        contexto["titulo_ativo"] = (
            TituloConcedido.objects.filter(
                usuario=request.user, ativo=True, titulo__ativo=True
            )
            .select_related("titulo")
            .first()
        )
        contexto["missoes_ativas"] = [
            item
            for item in resumo_missoes(request.user)
            if item["status"] in {"disponivel", "em_andamento"}
        ][:3]
    return render(
        request,
        "contas/inicio.html",
        contexto,
    )


@login_required
def perfil(request):
    if request.user.papel != Usuario.Papel.ALUNO:
        raise PermissionDenied
    perfil_aluno = getattr(request.user, "perfil_aluno", None)
    if perfil_aluno is None:
        raise PermissionDenied

    if request.method == "POST":
        form = PerfilAlunoForm(
            request.POST, request.FILES, instance=perfil_aluno, usuario=request.user
        )
        if form.is_valid():
            foto_anterior = perfil_aluno.foto.name if perfil_aluno.foto else None
            fundo_anterior = (
                perfil_aluno.imagem_fundo.name if perfil_aluno.imagem_fundo else None
            )
            perfil_salvo = form.save()
            form.salvar_titulo_ativo()
            foto_atual = perfil_salvo.foto.name if perfil_salvo.foto else None
            fundo_atual = (
                perfil_salvo.imagem_fundo.name if perfil_salvo.imagem_fundo else None
            )
            if foto_anterior and foto_anterior != foto_atual:
                default_storage.delete(foto_anterior)
            if fundo_anterior and fundo_anterior != fundo_atual:
                default_storage.delete(fundo_anterior)
            return redirect("perfil")
    else:
        form = PerfilAlunoForm(instance=perfil_aluno, usuario=request.user)
    return render(request, "contas/perfil.html", {"form": form})


@login_required
def ranking(request):
    if request.user.papel != Usuario.Papel.ALUNO:
        raise PermissionDenied
    perfil_aluno = getattr(request.user, "perfil_aluno", None)
    if perfil_aluno is None:
        raise PermissionDenied

    categorias = {"fundamental": "Fundamental", "medio": "Médio", "global": "Global"}
    categoria_padrao = "medio" if perfil_aluno.serie.startswith("M") else "fundamental"
    categoria = request.GET.get("categoria", categoria_padrao)
    if categoria not in categorias:
        categoria = categoria_padrao
    periodo_tipo = request.GET.get("periodo", "temporada")
    if periodo_tipo not in {"temporada", "anual"}:
        periodo_tipo = "temporada"

    xp_atual = resumo_xp(request.user)
    periodo = xp_atual["periodo_anual"] if periodo_tipo == "anual" else xp_atual["temporada"]
    campo_periodo = "periodo_anual" if periodo_tipo == "anual" else "temporada"
    xp_do_periodo = (
        XPTransacao.objects.filter(
            usuario_id=OuterRef("usuario_id"),
            validada=True,
        )
        .filter(**{campo_periodo: periodo})
        .order_by()
        .values("usuario_id")
        .annotate(total=Sum("xp"))
        .values("total")[:1]
    )
    perfis = PerfilAluno.objects.filter(
        usuario__papel=Usuario.Papel.ALUNO,
        participar_ranking=True,
    )
    if categoria == "fundamental":
        perfis = perfis.filter(serie__startswith="F")
    elif categoria == "medio":
        perfis = perfis.filter(serie__startswith="M")
    linhas = list(
        perfis
        .annotate(
            xp=Coalesce(
                Subquery(xp_do_periodo, output_field=IntegerField()),
                Value(0),
                output_field=IntegerField(),
            )
        )
        .values("usuario_id", "apelido_ranking", "xp")
        .order_by("-xp", "apelido_ranking")
    )
    posicao_usuario = None
    posicao_anterior = 0
    xp_anterior = None
    for indice, linha in enumerate(linhas, start=1):
        if linha["xp"] != xp_anterior:
            posicao_anterior = indice
            xp_anterior = linha["xp"]
        linha["posicao"] = posicao_anterior
        if linha["usuario_id"] == request.user.pk:
            posicao_usuario = posicao_anterior

    return render(
        request,
        "contas/ranking.html",
        {
            "ranking": linhas[:50],
            "periodo": periodo,
            "periodo_tipo": periodo_tipo,
            "periodo_label": "ano atual" if periodo_tipo == "anual" else "temporada mensal",
            "categoria": categoria,
            "categoria_label": categorias[categoria],
            "participa_ranking": perfil_aluno.participar_ranking,
            "posicao_usuario": posicao_usuario,
            "xp_pontuacao": xp_atual["xp_anual" if periodo_tipo == "anual" else "xp_temporada"],
            "total_participantes": len(linhas),
        },
    )


@login_required
def resultados_ranking(request):
    if request.user.papel != Usuario.Papel.ALUNO:
        raise PermissionDenied
    if not hasattr(request.user, "perfil_aluno"):
        raise PermissionDenied

    agrupados = {}
    for resultado in (
        ResultadoRanking.objects.filter(periodo__fechado=True)
        .select_related("periodo")
        .order_by("-periodo__inicio", "categoria", "posicao")
    ):
        periodo = agrupados.setdefault(
            resultado.periodo_id,
            {
                "periodo": resultado.periodo,
                "categorias": {"fundamental": [], "medio": [], "global": []},
            },
        )
        periodo["categorias"][resultado.categoria].append(resultado)
    return render(
        request,
        "contas/resultados_ranking.html",
        {"periodos_resultado": list(agrupados.values())},
    )


@login_required
@require_GET
def foto_perfil(request, usuario_id):
    perfil_aluno = get_object_or_404(
        PerfilAluno.objects.select_related("usuario"), usuario_id=usuario_id
    )
    if request.user.pk != usuario_id and not perfil_aluno.foto_publica:
        raise Http404
    if not perfil_aluno.foto:
        raise Http404

    extensao = os.path.splitext(perfil_aluno.foto.name)[1].lower()
    tipos = {".jpg": "image/jpeg", ".png": "image/png"}
    content_type = tipos.get(extensao)
    if content_type is None:
        raise Http404
    try:
        resposta = FileResponse(
            perfil_aluno.foto.open("rb"), content_type=content_type
        )
    except OSError as exc:
        raise Http404 from exc
    resposta["Cache-Control"] = "private, no-store"
    resposta["X-Content-Type-Options"] = "nosniff"
    resposta["Referrer-Policy"] = "no-referrer"
    resposta["Content-Disposition"] = (
        f'inline; filename="foto-perfil{extensao}"'
    )
    return resposta


@login_required
@require_GET
def imagem_fundo_perfil(request):
    if request.user.papel != Usuario.Papel.ALUNO:
        raise Http404
    perfil_aluno = get_object_or_404(PerfilAluno, usuario=request.user)
    if not perfil_aluno.imagem_fundo:
        raise Http404

    extensao = os.path.splitext(perfil_aluno.imagem_fundo.name)[1].lower()
    tipos = {".jpg": "image/jpeg", ".png": "image/png"}
    content_type = tipos.get(extensao)
    if content_type is None:
        raise Http404
    try:
        resposta = FileResponse(
            perfil_aluno.imagem_fundo.open("rb"), content_type=content_type
        )
    except OSError as exc:
        raise Http404 from exc
    resposta["Cache-Control"] = "private, no-store"
    resposta["X-Content-Type-Options"] = "nosniff"
    resposta["Referrer-Policy"] = "no-referrer"
    resposta["Content-Disposition"] = (
        f'inline; filename="fundo-perfil{extensao}"'
    )
    return resposta
