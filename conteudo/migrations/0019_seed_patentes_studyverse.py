from django.db import migrations


FASES = (
    (
        "Patente I: Iniciante / Aprendiz",
        "Fase inicial de adaptação, criação de rotina e primeiros contatos com o estudo.",
        (
            "Recruta do Conhecimento",
            "Explorador de Páginas",
            "Guardião do Caderno",
            "Aprendiz Curioso",
            "Iniciado Acadêmico",
        ),
    ),
    (
        "Patente II: Praticante",
        "Consolidação da disciplina, leitura frequente e organização dos métodos.",
        (
            "Buscador de Respostas",
            "Praticante da Leitura",
            "Organizador de Ideias",
            "Desbravador de Conceitos",
            "Estrategista de Estudos",
        ),
    ),
    (
        "Patente III: Construtor",
        "Geração de conteúdo próprio, resumos, mapas mentais e sínteses.",
        (
            "Arquiteto de Resumos",
            "Mapeador de Conteúdo",
            "Construtor de Repertório",
            "Sintetizador de Conhecimento",
            "Articulador de Ideias",
        ),
    ),
    (
        "Patente IV: Analista",
        "Desenvolvimento de raciocínio crítico, resolução de problemas e aprofundamento.",
        (
            "Investigador de Hipóteses",
            "Analista de Fundamentos",
            "Raciocinador Lógico",
            "Solucionador de Exercícios",
            "Pesquisador Dedicado",
        ),
    ),
    (
        "Patente V: Especialista",
        "Domínio de matérias específicas e alta capacidade de retenção de conteúdo.",
        (
            "Especialista em Foco",
            "Mestre dos Cartões (Flashcards)",
            "Detentor da Memória",
            "Analista de Padrões",
            "Domador de Conteúdos",
        ),
    ),
    (
        "Patente VI: Erudito",
        "Visão ampla e interligada entre diferentes disciplinas e áreas do saber.",
        (
            "Conectador de Saberes",
            "Erudito Interdisciplinar",
            "Navegador Científico",
            "Mentor do Saber",
            "Especialista Avançado",
        ),
    ),
    (
        "Patente VII: Mestre",
        "Capacidade de ensinar, debate técnico e aplicação prática dos estudos.",
        (
            "Estrategista Acadêmico",
            "Didático Ensaiador",
            "Mestre da Retenção",
            "Debatedor de Teorias",
            "Mentor Acadêmico",
        ),
    ),
    (
        "Patente VIII: Guardião",
        "Referência no ambiente de estudos, resiliência extrema e consistência diária.",
        (
            "Guardião da Disciplina",
            "Pilar da Consistência",
            "Sábio do Foco",
            "Veterano do Conhecimento",
            "Vanguarda dos Estudos",
        ),
    ),
    (
        "Patente IX: Filósofo",
        "Inovação, capacidade de síntese complexa e geração de novos pensamentos.",
        (
            "Pensador Autônomo",
            "Arquiteto de Teorias",
            "Visionário da Sabedoria",
            "Filósofo Contemporâneo",
            "Líder Intelectual",
        ),
    ),
    (
        "Patente X: Supremo / Ilustre",
        "O topo da jornada de aprendizado contínuo (Lifelong Learner).",
        (
            "Supremo do Saber",
            "Grão-Mestre da Aprendizagem",
            "Sábio Ilustre",
            "Lenda Acadêmica",
            "Iluminado pelo Conhecimento",
        ),
    ),
)


def cadastrar_patentes(apps, schema_editor):
    Patente = apps.get_model("conteudo", "Patente")
    if Patente.objects.exists():
        return

    registros = []
    ordem = 0
    for fase, descricao, nomes in FASES:
        for nome in nomes:
            registros.append(
                Patente(
                    nome=nome,
                    descricao=f"{fase}. {descricao}",
                    xp_minimo=ordem * 100,
                    ativa=True,
                )
            )
            ordem += 1
    Patente.objects.bulk_create(registros)


class Migration(migrations.Migration):
    dependencies = [
        ("conteudo", "0018_notaavaliacao"),
    ]

    operations = [migrations.RunPython(cadastrar_patentes, migrations.RunPython.noop)]
