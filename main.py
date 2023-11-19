import json
from metrics import get_metrics, handleregionInput
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

@app.get("/")
def read_root():
    return {"FASTAPI TESTING UI"}

class data(BaseModel):
    annotated_mask: str  
    currentsection: int
    biosample: str
    coords: list
    ontologyTree:str

@app.post("/comparemasks/")
async def compare_masks(masks: data):
    currentsection  = masks.currentsection
    annotated_mask   = masks.annotated_mask
    biosample       = masks.biosample
    Coords          = masks.coords
    ontologyTree    =masks.ontologyTree
    print(currentsection,annotated_mask,biosample,Coords,ontologyTree)
    return get_metrics(currentsection,biosample,annotated_mask,Coords,ontologyTree)

class RegionDataRequest(BaseModel):
    currentsection: str
    geojson: str
    biosample: str
    
    
@app.post("/getRegionData/")
async def get_region_data(data: RegionDataRequest):
    currentsection = data.currentsection
    geojson = data.geojson
    biosample = data.biosample
    return handleregionInput(currentsection,geojson,biosample)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
