# StudyVerse

Plataforma educacional em desenvolvimento, feita com Django. Esta pasta contém
o projeto que já existia no workspace; a implementação seguirá em etapas para
preservar o que funciona e evitar apresentar ideias futuras como recursos prontos.

## Requisitos atuais

- Windows e Python 3.12 ou superior (o ambiente existente usa Python 3.14).
- Dependências listadas em `requirements.txt`.

## Preparar e iniciar no Windows

No terminal do VS Code, na pasta do projeto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Se o ambiente virtual `.venv` já estiver criado, ative-o e siga a partir da
instalação das dependências. A aplicação local fica em <http://127.0.0.1:8000/>;
o painel administrativo fica em <http://127.0.0.1:8000/admin/>.

## Configuração

`config/settings.py` usa variáveis de ambiente com prefixo `DJANGO_`. O arquivo
`.env.example` documenta os nomes e valores de exemplo; o Django não lê arquivos
`.env` sozinho. No PowerShell, configure-as antes de iniciar o servidor, por
exemplo:

```powershell
$env:DJANGO_SECRET_KEY = "uma-chave-local"
$env:DJANGO_DEBUG = "true"
$env:DJANGO_ALLOWED_HOSTS = "localhost,127.0.0.1"
```

O valor padrão de `SECRET_KEY` serve somente para desenvolvimento local. Para
publicar o sistema, configure uma chave privada e `DJANGO_DEBUG=false` no
ambiente de hospedagem. Não coloque chaves reais no repositório.

## Publicar com GitHub, Supabase e Render

O GitHub guarda o código, o Supabase fornece o PostgreSQL e o Render executa o
Django. O GitHub Pages não executa esta aplicação Django. O arquivo `Procfile`
inicia a aplicação com Waitress, que também é compatível com o ambiente Windows
usado para desenvolvimento.

1. Crie um projeto no Supabase e copie a URL de conexão do **Session pooler**
   (menu **Connect**). Use a URL completa como `DATABASE_URL`; a senha fica
   somente nas variáveis secretas da hospedagem, nunca no GitHub. O Django
   exige conexão SSL em produção.
2. Envie o código ao GitHub. Antes de confirmar o envio, confira `git status`:
   não publique `.env`, `studyverse_secret_key.txt`, `db.sqlite3`, `media/` ou
   backups.
3. Crie no Render um serviço Web conectado ao repositório. Use o comando de
   build `pip install -r requirements.txt && python manage.py collectstatic --noinput`
   e o comando de início
   `python manage.py migrate && waitress-serve --listen=0.0.0.0:$PORT config.wsgi:application`.
4. Gere uma chave com
   `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
   e configure no Render as variáveis `DJANGO_SECRET_KEY`,
   `DJANGO_DEBUG=false`, `DATABASE_URL`, `DJANGO_ALLOWED_HOSTS` (o domínio do
   serviço, sem `https://`) e `DJANGO_CSRF_TRUSTED_ORIGINS` (o mesmo domínio
   com `https://`). Em produção, o app exige uma chave aleatória com pelo menos
   50 caracteres, força HTTPS e ativa HSTS por um ano.
5. Configure armazenamento persistente privado para os uploads. O app salva
   fotos e PDFs no disco, e o disco temporário de uma hospedagem pode apagá-los
   em reinicializações ou novos deploys. Se montar um disco persistente em
   `/var/data`, configure também `STUDYVERSE_DATA_DIR=/var/data`. Não torne esse
   diretório público: os arquivos são servidos por views autenticadas.
6. Depois da primeira inicialização e das migrações, crie o administrador pelo
   shell do serviço com `python manage.py createsuperuser`.

O arquivo `.env.example` lista os nomes das variáveis; ele é apenas referência,
não é carregado automaticamente. Não use a chave `service_role` do Supabase no
navegador nem a publique no GitHub. Faça também backups do banco e do disco de
uploads. O conteúdo do SQLite local não é transferido automaticamente para o
Supabase.

## O que existe hoje

- Projeto Django com autenticação baseada no usuário personalizado `Usuario`.
- Cadastro de aluno com série e confirmação do aviso informado no formulário.
- Cadastro de professor usando código armazenado como hash, gerenciado pelo
  admin.
- Edição do nome de exibição e escolha de avatar para o perfil do aluno.
- Envio opcional de foto de perfil JPEG/PNG até 5 MB, redimensionada para no
  máximo 512 × 512 e regravada sem metadados EXIF. A exibição exige login e
  respeita a preferência de privacidade do aluno.
- Envio de imagem de fundo JPEG/PNG até 5 MB para personalizar o cartão da
  página inicial. Ela é redimensionada, regravada sem metadados EXIF e servida
  somente ao próprio aluno; também é possível removê-la no perfil.
- Catálogo de matérias em destaque e assuntos por série.
- Biblioteca com tipo de material, dificuldade, objetivos de aprendizagem,
  palavras-chave, fonte de referência e busca/filtro por texto e tipo. Professores
  podem anexar PDFs de até 20 MB; os arquivos só são entregues pela view autenticada
  quando o material está publicado.
- Leitor de materiais com trechos endereçados pelo texto, marcações privadas,
  etiquetas e anotações pessoais.
- Perguntas e respostas entre estudantes da mesma série: professores aprovam ou
  rejeitam cada publicação antes de ela ficar visível aos colegas; autores veem
  seus próprios envios pendentes, sem expor sua identidade nas discussões.
  Professores e administradores podem, em controles separados, bloquear a
  colagem nos campos de envio dessas perguntas e respostas.
- Quizzes individuais de múltipla escolha, tentativas corrigidas no servidor e
  revisão das respostas depois do envio, com histórico privado do aluno.
- Quiz Arena 1 contra 1 por convite de uso único, com dez questões copiadas para
  um retrato imutável, respostas ocultas até ambos terminarem, apuração no
  servidor, empate e expiração em 48 horas. A versão atual não aposta nem concede
  XP em partidas.
- XP de quiz com transações idempotentes e contadores de temporada, ano e vida
  calculados a partir do histórico. A recompensa fica desativada até ser
  configurada no admin.
- 50 patentes iniciais calculadas a partir do XP vitalício validado, em degraus
  de 100 XP (de 0 a 4.900). O administrador pode editar os limites e cadastrar
  outras patentes no Django Admin.
- Títulos cadastrados e concedidos pelo admin; alunos escolhem qual título
  recebido aparece no perfil.
- Rankings Fundamental, Médio e Global, mensais ou do ano atual, com
  participação opcional e apenas o apelido público escolhido pelo aluno.
- Fechamento administrativo de períodos concluídos, com resultados de ranking
  congelados e página autenticada de histórico por categoria.
- Conquistas configuráveis por meta de quizzes concluídos, quizzes perfeitos
  ou XP vitalício; o desbloqueio fica registrado por aluno.
- Missões administráveis por meta de quizzes concluídos ou perfeitos, prazo
  opcional, recompensa configurável em XP e progresso individual.
- Painel para professores cadastrarem matérias, assuntos e quizzes com questões; os
  registros ficam vinculados ao professor autenticado no servidor. Quizzes
  com tentativas ficam protegidos; o professor pode duplicá-los como rascunho
  para criar uma nova versão sem alterar o histórico. Rascunhos sem tentativas
  podem ser excluídos pelo próprio professor.
- Caderneta do professor com filtros por quiz e série, média de acertos por
  aluno e tentativas recentes dos quizzes criados pelo próprio professor;
  também permite lançar, editar e excluir notas de avaliações. Cada aluno
  consulta apenas suas próprias notas.
- Banco SQLite local (`db.sqlite3`) e migrações versionadas.
- Templates base e folhas de estilo iniciais.

Para habilitar XP de quiz, entre no Django Admin, abra **Regras de XP**, crie a
atividade **Conclusão de quiz**, informe a quantidade de XP e marque a regra
como ativa. Nenhum valor é presumido: sem uma regra ativa, tentativas e
resultados são registrados, mas não concedem XP.

As 50 patentes iniciais são criadas pela migração de dados. Para alterar os
limites de XP ou adicionar outras, abra **Patentes** no Django Admin. A tela
inicial mostra o nível atual e o progresso até o próximo. Contas de professor
sem acesso de equipe ao Django Admin não gerenciam patentes.

Para criar e conceder títulos, cadastre o título em **Títulos** e depois
conceda-o ao aluno em **Títulos concedidos**. O aluno pode selecionar o título
recebido na página **Meu perfil**. O sistema não concede títulos
automaticamente, pois os critérios ainda precisam ser definidos.

Para criar uma missão, abra **Missões** no admin, escolha se a meta conta
quizzes concluídos ou quizzes com 100% de acerto, configure a quantidade, o
período e a recompensa. Missões começam desativadas e não há dados de exemplo.
O progresso é calculado no servidor a partir das tentativas registradas.

Para encerrar uma temporada mensal ou um ano, abra **Períodos de XP** no admin,
selecione somente períodos que já terminaram e escolha **Fechar períodos
concluídos e registrar rankings**. O sistema impede o fechamento antes da data
final e registra uma cópia dos resultados Fundamental, Médio e Global. Alunos
conectados podem consultar as cópias em **Ranking → resultados de períodos
encerrados**; o fechamento pode ser repetido sem duplicar resultados.

## Ainda não implementado

desafios PvP com aposta de XP e outros formatos de arquivo além de PDF ainda
não estão construídos. A caderneta permite lançar avaliações, mas ainda não há
vínculo formal de turmas entre professores e alunos. O banco usado no
desenvolvimento é local; a configuração para PostgreSQL/Supabase está pronta,
mas ainda não há banco hospedado nem implantação online configurados. Os arquivos
`contas/tests.py` e `conteudo/tests.py` cobrem os fluxos básicos já implementados;
as regras dos recursos futuros ainda precisarão de testes próprios. Fotos ficam
em `media/` e são entregues por uma view autenticada, não por uma URL pública de
arquivos estáticos. O bloqueio de colagem é aplicado no navegador; pode ser
contornado e não funciona como detector de plágio. Em produção, o armazenamento
também deve permanecer privado.

## Estrutura principal

- `config/`: configurações e rotas centrais do Django.
- `contas/`: autenticação, cadastro, usuários e perfis.
- `conteudo/`: matérias, assuntos e telas relacionadas.
- `db.sqlite3`: banco de desenvolvimento local.

## Próximas etapas

1. Revisar a suíte completa de testes e as configurações de produção.
2. Associar professores a turmas e limitar os lançamentos à sua lista de alunos.
3. Planejar banco hospedado, armazenamento privado, backups e implantação.
4. Decidir se a Arena terá apostas de XP e se a biblioteca aceitará outros
   formatos de arquivo.
