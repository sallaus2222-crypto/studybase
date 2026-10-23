from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("cadastro/", views.cadastro_aluno, name="cadastro"),
    path("cadastro-professor/", views.cadastro_professor, name="cadastro_professor"),
    path("perfil/", views.perfil, name="perfil"),
    path("ranking/", views.ranking, name="ranking"),
    path("ranking/resultados/", views.resultados_ranking, name="resultados_ranking"),
    path("perfil/foto/<int:usuario_id>/", views.foto_perfil, name="foto_perfil"),
    path("perfil/imagem-fundo/", views.imagem_fundo_perfil, name="imagem_fundo_perfil"),
    path(
        "entrar/",
        auth_views.LoginView.as_view(template_name="contas/login.html"),
        name="login",
    ),
    path("sair/", auth_views.LogoutView.as_view(), name="logout"),
]
