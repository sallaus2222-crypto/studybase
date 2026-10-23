from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contas", "0005_perfilaluno_apelido_ranking_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="perfilaluno",
            name="imagem_fundo",
            field=models.ImageField(
                blank=True, upload_to="fundos-perfil/%Y/%m/"
            ),
        ),
    ]
