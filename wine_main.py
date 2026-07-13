from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import joblib
import numpy as np
import sqlite3
import time
import traceback
from wine_schemas import WineInput, WineOutput
from wine_database import init_db, log_prediction, log_incident
from wine_monitoring import start_monitoring, on_new_request

@asynccontextmanager
async def lifespan(app: FastAPI): #jednom se izvrsava
    init_db()
    start_monitoring()
    yield

#definisanje app i pozive prethodne fje
app = FastAPI(title="Wine Quality API", lifespan=lifespan)

app.add_middleware( #nema ogranicenja domaina, sve je dozvoljeno 
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    model = joblib.load("final_model.joblib") #prethodno prunovan model, samo jednom se ucitava
except Exception as e:
    #pad pri startu, upisuje se u incidents tabelu
    print(f"[Startup] Neuspesno ucitavanje modela:\n{traceback.format_exc()}", flush=True)
    try:
        init_db()
        log_incident("model_load_failed", {}, f"{type(e).__name__}: {e}")
    except Exception as db_err:
        print(f"[Startup] Neuspesno logovanje incidenta pri startu: {db_err!r}", flush=True)
    raise

@app.exception_handler(RequestValidationError) #umesto default salje se ova fja
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    body = await request.json()
    log_prediction(input_data=body, status="validation_error")
    return JSONResponse(status_code=422, content={"detail": exc.errors()})

@app.get("/") #provera da li server radi
def root():
    return {"status": "ok", "message": "Wine Quality API radi"}

@app.post("/predict", response_model=WineOutput) #obradjuju se POST zahtevi na putanji /predict
#oblik odgovora je u wineoutput, napisan u wine_schemas

def predict(input_data: WineInput): #pretvaranje zahteva u wineinuput objekat
    start_time = time.time() #belezi vreme radi kansijeg racunanja

    try:
        features = np.array([[ #svih 11 vrednosti iz inputa idu u niz
        #dole su konkretne vrednosti koje je korisnik uneo
            input_data.fixed_acidity,
            input_data.volatile_acidity,
            input_data.citric_acid,
            input_data.residual_sugar,
            input_data.chlorides,
            input_data.free_sulfur_dioxide,
            input_data.total_sulfur_dioxide,
            input_data.density,
            input_data.pH,
            input_data.sulphates,
            input_data.alcohol
        ]])

        prediction = model.predict(features)[0] #salju se dobijene karakteristike modelu
        #uzima se izlaz modela 0 ili 1
        probability = model.predict_proba(features)[0][1] #vraca verovatnoce za svaku klasu

        if prediction not in [0, 1] or not np.isfinite(probability) or not (0 <= probability <= 1):
            #sustinski nemoguce da se desi uvek se vraca 0,1. ovo je slucaj ako je model ostecen ili pogresnog tipa
            print(f"[Sanity check] Neispravan izlaz modela: prediction={prediction!r}, probability={probability!r}, input={input_data.model_dump()!r}", flush=True)
            response_time = (time.time() - start_time) * 1000 #vreme obrade do ovog trenutka, u ovom slucaju (1)
            log_prediction(input_data.model_dump(), None, None, response_time, "invalid_output")
            log_incident( #posebna tabela za ovaj slucaj nevalidnog izlaza
                "invalid_output",
                input_data.model_dump(),
                f"prediction={prediction!r}, probability={probability!r}"
            )
            raise HTTPException(status_code=500, detail="Trenutno ne mozemo obraditi zahtev.") #korisniku se ne prosledjuje izlaz iz modela u ovom slucaju

        confidence = probability if prediction == 1 else 1 - probability  #sigurnost u predvidjenu klasu, ako je izlaz prosao proveru validnosti

        label = "dobro vino" if prediction == 1 else "lose vino" #1 dobro, 0 lose

        if confidence < 0.55: #nizak prag sigurnosti. vraca se labela, ali se to napominje
            message = f"Model nije dovoljno siguran, {confidence*100:.1f}% sigurnosti. Uzmite ovaj rezultat sa rezervom."
            status = "low_confidence"
        else:
            message = f"Model je {confidence*100:.1f}% siguran da je ovo {label}"
            status = "success"

        response_time = (time.time() - start_time) * 1000 ##vreme obrade do ovog trenutka, u ovom slucaju (2)

        log_prediction(input_data.model_dump(), label, round(confidence, 4), response_time, status) #loggovanje predikcije

        if status in ("success", "low_confidence"):   #fja za brojanje zahteva na svaki 100-ti drift i latencija
            try:
                on_new_request()
            except Exception as e: #slucaj neuspesnog monitoringa
                print(f"[Monitoring] Greska: {e}", flush=True)

        return WineOutput(label=label, probability=round(confidence, 4), message=message) #vracanje izlaza po semi 

    except HTTPException:
        #namerno bacene greske su vec ulogovane iznad, samo se prosledjuju dalje
        raise
    except Exception as e:
        #bilo koja neocekivana greska
        response_time = (time.time() - start_time) * 1000  ##vreme obrade do ovog trenutka, u ovom slucaju (3)
        print(f"[Unhandled] Neocekivana greska u /predict:\n{traceback.format_exc()}", flush=True)
        try:
            log_prediction(input_data.model_dump(), None, None, response_time, "unhandled_exception")
        except Exception as db_err:
            print(f"[Unhandled] Neuspesno logovanje u predictions: {db_err!r}", flush=True)
        try:
            log_incident("unhandled_exception", input_data.model_dump(), f"{type(e).__name__}: {e}")
        except Exception as db_err:
            print(f"[Unhandled] Neuspesno logovanje incidenta: {db_err!r}", flush=True)
        raise HTTPException(status_code=500, detail="Trenutno ne mozemo obraditi zahtev.")

@app.get("/predictions") #hvatanje greske ako baza padne
def get_predictions():
    try:
        with sqlite3.connect("predictions.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM predictions ORDER BY timestamp DESC LIMIT 20") #poslednjih 20 iz baze za uvid
            rows = cursor.fetchall()
        return {"predictions": rows}
    except Exception as e:
        print(f"[Unhandled] Neocekivana greska u /predictions:\n{traceback.format_exc()}", flush=True)
        try:
            log_incident("unhandled_exception", {}, f"endpoint=/predictions, {type(e).__name__}: {e}")
        except Exception as db_err:
            print(f"[Unhandled] Neuspesno logovanje incidenta: {db_err!r}", flush=True)
        raise HTTPException(status_code=500, detail="Trenutno ne mozemo obraditi zahtev.")

@app.get("/monitoring/latency")
def get_latency():
    try:
        with sqlite3.connect("predictions.db") as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, avg_latency, min_latency, max_latency, p95_latency, median_latency, num_requests
                FROM monitoring_logs ORDER BY timestamp DESC LIMIT 20
            """)
            rows = cursor.fetchall()
        return {"latency_checks": rows}
    except Exception as e:
        print(f"[Unhandled] Neocekivana greska u /monitoring/latency:\n{traceback.format_exc()}", flush=True)
        try:
            log_incident("unhandled_exception", {}, f"endpoint=/monitoring/latency, {type(e).__name__}: {e}")
        except Exception as db_err:
            print(f"[Unhandled] Neuspesno logovanje incidenta: {db_err!r}", flush=True)
        raise HTTPException(status_code=500, detail="Trenutno ne mozemo obraditi zahtev.")