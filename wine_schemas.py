from pydantic import BaseModel, Field
#validaicja ulaznih podataka
#opsezi nisu iz dataseta vec max fizicki moguci
class WineInput(BaseModel):
    fixed_acidity: float = Field(ge=3.5, le=20)
    volatile_acidity: float = Field(gt=0, le=2)
    citric_acid: float = Field(ge=0, le=1)
    residual_sugar: float = Field(gt=0, le=20)
    chlorides: float = Field(gt=0, le=1)
    free_sulfur_dioxide: float = Field(gt=0, le=400)
    total_sulfur_dioxide: float = Field(gt=0, le=300)
    density: float = Field(gt=0.98, le=1.05)
    pH: float = Field(gt=2.5, le=5)
    sulphates: float = Field(gt=0, le=10)
    alcohol: float = Field(gt=8, le=20)
class WineOutput(BaseModel):
    label: str
    probability: float
    message: str
    