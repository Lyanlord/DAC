import os
import glob
import sqlite3
import pandas as pd

# =====================================================================
# 1. LÓGICA E ESTRUTURA (CLASSES DE ORIENTAÇÃO A OBJETOS)
# =====================================================================
class RegistroAnual:
    """Classe que representa os indicadores de uma escola em um ano específico."""
    def __init__(self, ano, matriculas, aprovados, reprovados, abandono):
        self.ano = ano
        self.matriculas = int(matriculas)
        self.aprovados = int(aprovados)
        self.reprovados = int(reprovados)
        self.abandono = int(abandono)

    def taxa_aprovacao(self):
        return (self.aprovados / self.matriculas * 100) if self.matriculas > 0 else 0.0

    def taxa_abandono(self):
        return (self.abandono / self.matriculas * 100) if self.matriculas > 0 else 0.0


class Escola:
    """Classe que representa uma Unidade Escolar e seu histórico."""
    def __init__(self, nome, municipio):
        self.nome = nome
        self.municipio = municipio
        self.historico = {}  # Dicionário organizando os anos em memória: {ano: RegistroAnual}

    def adicionar_registro(self, registro: RegistroAnual):
        self.historico[registro.ano] = registro


# =====================================================================
# 2. PERSISTÊNCIA RELACIONAL E PROCESSAMENTO DE DADOS (ETL)
# =====================================================================
class GestorBancoDados:
    """Gerencia a criação e inserção de dados no banco de dados SQLite."""
    def __init__(self, nome_banco="educacao_ms.db"):
        self.conn = sqlite3.connect(nome_banco)
        self.cursor = self.conn.cursor()
        self._criar_tabelas()

    def _criar_tabelas(self):
        self.cursor.executescript('''
            CREATE TABLE IF NOT EXISTS municipio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT UNIQUE NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS escola (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                municipio_id INTEGER,
                FOREIGN KEY(municipio_id) REFERENCES municipio(id),
                UNIQUE(nome, municipio_id)
            );
            
            CREATE TABLE IF NOT EXISTS registro_anual (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                escola_id INTEGER,
                ano INTEGER,
                matriculas_total INTEGER,
                aprovados INTEGER,
                reprovados INTEGER,
                abandono INTEGER,
                FOREIGN KEY(escola_id) REFERENCES escola(id),
                UNIQUE(escola_id, ano)
            );
        ''')
        self.conn.commit()

    def carregar_dados_dos_csvs(self):
        arquivos_csv = glob.glob('matriculas-por-unidade-escolar-*.csv')
        if not arquivos_csv:
            print("Nenhum arquivo CSV encontrado no diretório atual.")
            return False

        print("Lendo arquivos CSV e processando dados para o Banco SQL... (Isso pode levar alguns segundos)")
        
        for arquivo in arquivos_csv:
            # Tratamento de leitura (tenta ponto-e-vírgula e vírgula)
            try:
                df = pd.read_csv(arquivo, sep=';', encoding='utf-8')
                if len(df.columns) < 2:
                    df = pd.read_csv(arquivo, sep=',', encoding='utf-8')
            except Exception as e:
                print(f"Erro ao ler {arquivo}: {e}")
                continue
            
            # Limpeza de dados nulos
            df.fillna(0, inplace=True)
            
            # Persistência Relacional linha a linha
            for _, row in df.iterrows():
                ano = row.get('AnoReferencia', 0)
                mun_nome = str(row.get('NomeMunicipio', 'Desconhecido')).strip().upper()
                esc_nome = str(row.get('NomeUnidadeEscolar', 'Desconhecida')).strip()
                matriculas = row.get('MatriculasTotal', 0)
                aprov = row.get('Aprovados', 0)
                reprov = row.get('Reprovados', 0)
                aband = row.get('Abandono', 0)

                # Insere Município (ignora se já existe)
                self.cursor.execute('INSERT OR IGNORE INTO municipio (nome) VALUES (?)', (mun_nome,))
                self.cursor.execute('SELECT id FROM municipio WHERE nome = ?', (mun_nome,))
                mun_id = self.cursor.fetchone()[0]

                # Insere Escola
                self.cursor.execute('INSERT OR IGNORE INTO escola (nome, municipio_id) VALUES (?, ?)', (esc_nome, mun_id))
                self.cursor.execute('SELECT id FROM escola WHERE nome = ? AND municipio_id = ?', (esc_nome, mun_id))
                esc_id = self.cursor.fetchone()[0]

                # Insere Registro Anual
                self.cursor.execute('''
                    INSERT OR IGNORE INTO registro_anual 
                    (escola_id, ano, matriculas_total, aprovados, reprovados, abandono)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (esc_id, ano, matriculas, aprov, reprov, aband))
                
        self.conn.commit()
        print("Carga de dados concluída com sucesso!")
        return True


# =====================================================================
# 3. ANÁLISE E VISUALIZAÇÃO (INTERFACE / DASHBOARD)
# =====================================================================
class SistemaEducacional:
    """Sistema Principal que organiza as consultas e a interface de usuário."""
    def __init__(self, db: GestorBancoDados):
        self.db = db
        self.escolas_em_memoria = []

    def carregar_para_memoria(self, nome_municipio=None, ano_filtro=None):
        """Carrega os dados do SQL para as Estruturas de Dados Orientadas a Objetos."""
        self.escolas_em_memoria = []
        
        query = '''
            SELECT m.nome, e.nome, r.ano, r.matriculas_total, r.aprovados, r.reprovados, r.abandono 
            FROM registro_anual r
            JOIN escola e ON r.escola_id = e.id
            JOIN municipio m ON e.municipio_id = m.id
            WHERE 1=1
        '''
        params = []
        if nome_municipio:
            query += " AND m.nome LIKE ?"
            params.append(f"%{nome_municipio.upper()}%")
        if ano_filtro:
            query += " AND r.ano = ?"
            params.append(ano_filtro)
            
        self.db.cursor.execute(query, params)
        resultados = self.db.cursor.fetchall()

        # Construção da Estrutura OO
        escolas_dict = {}
        for row in resultados:
            mun_nome, esc_nome, ano, mat, apr, rep, abd = row
            chave_escola = f"{esc_nome}-{mun_nome}"
            
            if chave_escola not in escolas_dict:
                escolas_dict[chave_escola] = Escola(esc_nome, mun_nome)
                
            registro = RegistroAnual(ano, mat, apr, rep, abd)
            escolas_dict[chave_escola].adicionar_registro(registro)
            
        self.escolas_em_memoria = list(escolas_dict.values())
        return self.escolas_em_memoria

    def exibir_dashboard(self, municipio=None, ano=None):
        escolas = self.carregar_para_memoria(municipio, ano)
        
        if not escolas:
            print("\n[!] Nenhum dado encontrado para os filtros aplicados.")
            return

        total_mat = 0
        total_apr = 0
        total_abd = 0
        
        for escola in escolas:
            for _, reg in escola.historico.items():
                total_mat += reg.matriculas
                total_apr += reg.aprovados
                total_abd += reg.abandono

        taxa_apr = (total_apr / total_mat * 100) if total_mat > 0 else 0
        taxa_abd = (total_abd / total_mat * 100) if total_mat > 0 else 0

        # Interface do Dashboard
        print("\n" + "="*50)
        print(" 📊 DASHBOARD DA EDUCAÇÃO MS (ODS 4)".center(50))
        print("="*50)
        print(f"Filtro Município : {municipio.upper() if municipio else 'TODOS'}")
        print(f"Filtro Ano       : {ano if ano else 'SÉRIE HISTÓRICA COMPLETA'}")
        print("-" * 50)
        print(f"Escolas Analisadas  : {len(escolas)}")
        print(f"Total de Matrículas : {total_mat:,}")
        print(f"Total de Aprovados  : {total_apr:,}")
        print(f"Total de Abandonos  : {total_abd:,}")
        print("-" * 50)
        print(f"📈 Taxa de Aprovação : {taxa_apr:.2f}%")
        print(f"📉 Taxa de Abandono  : {taxa_abd:.2f}%")
        print("="*50)


def menu_interativo():
    print("Iniciando o Sistema Educacional...")
    db = GestorBancoDados()
    
    # Processa os arquivos CSV automaticamente na primeira execução
    if not db.carregar_dados_dos_csvs():
        return
        
    sistema = SistemaEducacional(db)
    
    while True:
        print("\n" + "="*40)
        print(" MENU DE ANÁLISE EDUCACIONAL (MS)")
        print("="*40)
        print("1. Ver panorama geral do estado (Todos os anos)")
        print("2. Filtrar por Município")
        print("3. Filtrar por Município e Ano")
        print("4. Avaliar evolução de um Município (Comparar anos)")
        print("5. Sair")
        
        escolha = input("\nSelecione uma opção: ")
        
        if escolha == '1':
            sistema.exibir_dashboard()
            
        elif escolha == '2':
            mun = input("Digite o nome do Município (ex: Campo Grande): ")
            sistema.exibir_dashboard(municipio=mun)
            
        elif escolha == '3':
            mun = input("Digite o nome do Município: ")
            try:
                ano = int(input("Digite o Ano (ex: 2021): "))
                sistema.exibir_dashboard(municipio=mun, ano=ano)
            except ValueError:
                print("Ano inválido!")
                
        elif escolha == '4':
            mun = input("Digite o nome do Município: ")
            print(f"\n--- Evolução Histórica de {mun.upper()} ---")
            for ano_teste in range(2018, 2027):
                # Testa se existe dado para aquele ano puxando os dados pro dashboard
                # Usamos um truque no display limitando as quebras de linha para ficar compacto
                escolas = sistema.carregar_para_memoria(nome_municipio=mun, ano_filtro=ano_teste)
                if escolas:
                    mat, apr, abd = 0, 0, 0
                    for e in escolas:
                        reg = e.historico.get(ano_teste)
                        if reg:
                            mat += reg.matriculas
                            apr += reg.aprovados
                            abd += reg.abandono
                    tx_apr = (apr/mat*100) if mat > 0 else 0
                    tx_abd = (abd/mat*100) if mat > 0 else 0
                    print(f"Ano {ano_teste}: Matrículas: {mat} | Aprovação: {tx_apr:.1f}% | Abandono: {tx_abd:.1f}%")
                    
        elif escolha == '5':
            print("Encerrando o sistema...")
            break
        else:
            print("Opção inválida.")

if __name__ == "__main__":
    menu_interativo()