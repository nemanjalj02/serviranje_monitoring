# Primena, serviranje i monitoring modela mašinskog učenja

Sistem za binarnu klasifikaciju kvaliteta crvenog vina (dobro/loše vino) na osnovu 11 fizičko-hemijskih obeležja, korišćenjem Random Forest modela. 


Dataset (winequality-red.csv, Kaggle) se deli na trening/validacioni/test skup (70:15:15), stratifikovano po klasi. 


HPO pretraga se radi Optuna bibliotekom (Bajesovska optimizacija) u dva kruga: prvi maksimizuje Precision nad širim opsegom parametara, drugi dodatno minimizuje veličinu modela (kroz težinski faktor alfa) uz suženiji opseg parametara i cost-complexity pruning (ccp_alpha). 


Oba modela (originalni i pruned) se ocenjuju na nezavisnom test skupu i bira se finalni na osnovu odnosa metrika i kompresije. 


Finalni model se servira kao FastAPI servis: ulazni podaci se validiraju (Pydantic), predikcija vraća labelu i procenu sigurnosti (uz upozorenje ako je poverenje ispod praga), a svaki zahtev (uspešan, nevalidan ili neuspeo), kao i eventualni incidenti (pad modela, neispravan izlaz, neobrađena greška) loguju se u SQLite bazu. Jednostavan HTML frontend omogućava ručno testiranje preko forme. Na svakih 100 uspešnih zahteva automatski se proveravaju latencija (avg/min/max/median/P95) i data drift u odnosu na trening podatke (Evidently, Kolmogorov-Smirnov test), a rezultati se čuvaju kao HTML izveštaji. 


Saobraćaj ka API-ju generiše posebna skripta koja simulira mešavinu validnih, nevalidnih i drift zahteva, dok se nad zabeleženim podacima naknadno pravi analiza rezultata (statusi zahteva, latencija, distribucija labela pre i tokom drifta).

## Sadržaj projekta
* RF_Model_wine.ipynb: Jupyter Notebook koji služi za dobijanje modela (dataset, split, HPO pretrage, pruning, finalna evaluacija na test skupu).
* wine_main.py: FastAPI aplikacija koja učitava model, izlaže `/predict` endpoint, pokreće logovanje i monitoring.
* wine_schemas.py: Pydantic šeme za validaciju ulaza i izlaza API-ja.
* wine_database.py: inicijalizacija SQLite baze i logovanje predikcija/incidenata.
* wine_monitoring.py: praćenje latencije i data drifta (Evidently), generisanje HTML izveštaja na svakih 100 validnih zahteva.
* simulate_requests.py: skripta koja simulira saobraćaj (validne, nevalidne i drift zahteve) radi testiranja API-ja i punjenja baze.
* db_report.py: sumarni izveštaj iz baze (statusi zahteva, latencija, monitoring logovi, distribucija labela pre/tokom drifta).
* index.html: jednostavan HTML frontend za ručno testiranje predikcije preko forme.
* final_model.joblib: finalni (pruned) istreniran model, koji učitava wine_main.py.
* winequality-red.csv: dataset korišćen za treniranje i kao referenca za drift monitoring.
* predictions.db: primer baze sa zabeleženim predikcijama iz jedne simulacije.
* reports/: primer generisanih drift izveštaja iz jedne simulacije.
* requirements.txt: spisak potrebnih Python biblioteka i njihovih tačnih verzija.


## Setup
1. Instalirati Python 3.10 ili noviji.
2. Instalirati biblioteke iz requirements.txt fajla.

Kreiranje i aktivacija virtuelnog okruženja (Windows):
```
python -m venv env
env\Scripts\activate
```

Kreiranje i aktivacija virtuelnog okruženja (Linux/Mac):
```
python -m venv env
source env/bin/activate
```

Instalacija zavisnosti:
```
pip install -r requirements.txt
```

## Run
Pokretanje API servera:
```
uvicorn wine_main:app --reload
```
Server je dostupan na `http://127.0.0.1:8000` (lokalna/loopback adresa). Dostupni endpointi: `/` (provera statusa), `/predict` (POST, predikcija), `/predictions` (poslednjih 20 zapisa iz baze), `/monitoring/latency` (poslednje zabeležene latencijske provere).

Za ručno testiranje preko forme, otvoriti index.html u browseru dok server radi lokalno.

Za simulaciju saobraćaja (i generisanje monitoring/drift izveštaja svakih 100 validnih zahteva):
```
python simulate_requests.py
```

Za sumarni izveštaj iz baze nakon simulacije:
```
python db_report.py
```

`predictions.db` i `reports/` u repou predstavljaju rezultate jednog konkretnog pokretanja `simulate_requests.py`, korišćene u prezentaciji/izveštaju. Za novu evidenciju, obrisati oba i ponovo pokrenuti simulaciju.

Notebook (RF_Model_wine.ipynb) se pokreće preko `jupyter notebook` ili `jupyter-lab` (ili direktno u editoru sa Jupyter podrškom). `final_model.joblib` je već gotov produkt tog notebook-a i nije neophodno ponovo trenirati model da bi se API pokrenuo.
