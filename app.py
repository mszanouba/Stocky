#!/usr/bin/env python
# coding: utf-8

# In[1]:


import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from fastapi import Request
from pydantic import BaseModel
import nbformat
from threading import Thread
import uvicorn
import nest_asyncio
from typing import List
import math
from fastapi.responses import JSONResponse
import pickle
import numpy as np
from sklearn.preprocessing import StandardScaler
import json
from io import BytesIO
from azure.storage.blob import BlobServiceClient
from alpha_vantage.timeseries import TimeSeries
import io
import sys
import matplotlib.pyplot as plt
import builtins


# In[2]:


connection_string = 'DefaultEndpointsProtocol=https;AccountName=stockanomaly;AccountKey=XCfgpf5eX6ZK1OBnGo+/DzOZQ8WsApNYvLuOGn2TbalNN3tpvvOQjjXGXYJbJ5xc9Wmip6LoOysj+AStfWHBNA==;EndpointSuffix=core.windows.net'
container_name = "containerstock"
blob_name = "MSFT.csv"

blob_service_client = BlobServiceClient.from_connection_string(connection_string)
container_client = blob_service_client.get_container_client(container_name)
blob_client = container_client.get_blob_client(blob_name)
blob_stream = blob_client.download_blob().readall()
data_blob = pd.read_csv(BytesIO(blob_stream), parse_dates=["Date"])


# In[3]:


last_date = data_blob["Date"].max()


# In[4]:


API_KEY = 'OYEDBWJJQM4XPHZ9'
SYMBOL = "MSFT"

def fetch_new_data(api_key, symbol, last_date):
    ts = TimeSeries(key=api_key, output_format="pandas")
    data, _ = ts.get_daily(symbol=symbol, outputsize="full")
    
    # Convertir l'index en colonne pour le filtrage
    data.reset_index(inplace=True)
    data.rename(columns={"index": "Date"}, inplace=True)
    
    # Filtrer les données plus récentes que `last_date`
    new_data = data[pd.to_datetime(data["date"]) > last_date]
    print(f"{len(new_data)} nouvelles lignes récupérées.")
    
    return new_data

# Appeler la fonction
new_data = fetch_new_data(API_KEY, SYMBOL, last_date)


# In[5]:


def rename_columns(new_data):
    new_data = new_data.rename(columns={
        "date"   : "Date",
        "1. open": "Open",
        "2. high": "High",
        "3. low": "Low",
        "4. close": "Close",
        "5. volume": "Volume"

    })
    return new_data
new_data= rename_columns(new_data)


# In[6]:


combined_data = pd.concat([data_blob, new_data], ignore_index=True)
combined_data = combined_data.drop_duplicates(subset="Date", keep="last").sort_values("Date")


# In[7]:


blob_client.upload_blob(combined_data.to_csv(index=False), overwrite=True)


# In[8]:


with open('MSFT_stocky.ipynb') as f:
    notebook_data = nbformat.read(f, as_version=4)

original_stdout = sys.stdout
sys.stdout = io.StringIO()

original_show = plt.show
original_print = builtins.print

def block_print(*args, **kwargs):
    pass  # Annule toute commande print

def block_show(*args, **kwargs):
    pass  # Annule plt.show()

builtins.print = block_print
plt.show = block_show

try:
    for cell in notebook_data['cells']:
        if cell['cell_type'] == 'code':
            code = cell['source']
            
            plt.ioff()  
            exec(code) 
            plt.close('all') 
finally:
   
    sys.stdout = original_stdout
    builtins.print = original_print
    plt.show = original_show
    plt.ion() 


# In[9]:


nest_asyncio.apply()


# In[10]:


app = FastAPI()


# In[11]:


class Features(BaseModel):
    Date: str
    Open: float
    High: float
    Low: float
    Close: float
    Adj_Close: float
    Volume: float
    PRV: float


# In[12]:


class MonthlyAnomaly(BaseModel):
    Month: str
    Anomalies: int
    Percentage_Change: float


# In[13]:


class Anomaly(BaseModel):
    Date: str
    Open: float
    Close: float
    High: float
    Low: float
    Anomaly: int


# In[14]:


templates = Jinja2Templates(directory="templates")  # Path to your 'templates' folder
app.mount("/static", StaticFiles(directory="static"), name="static")


# In[15]:


blob_name_new = "New_MSFT.csv"

blob_service_client_new = BlobServiceClient.from_connection_string(connection_string)
container_client_new = blob_service_client.get_container_client(container_name)
blob_client_new = container_client_new.get_blob_client(blob_name_new)
blob_stream_new = blob_client_new.download_blob().readall()
dff=pd.read_csv(BytesIO(blob_stream_new), parse_dates=["Date"])

@app.get("/anomalies", response_model=List[MonthlyAnomaly])
async def get_monthly_anomalies():
    
    dff["Date"] = pd.to_datetime(dff["Date"])
    current_year = pd.Timestamp.now().year
    yearly_data = dff[dff["Date"].dt.year == current_year]

    yearly_data = yearly_data.copy()
    yearly_data["Month"] = yearly_data["Date"].dt.month
    monthly_anomalies = yearly_data.groupby("Month").agg(
        Anomalies=("Anomaly", "sum") 
    ).reset_index()
    
    months = pd.DataFrame({"Month": range(1, 13)})
    monthly_anomalies = months.merge(monthly_anomalies, on="Month", how="left").fillna(0)
    
    monthly_anomalies["Anomalies"] = monthly_anomalies["Anomalies"].astype(int)
    monthly_anomalies["Percentage_Change"] = (
        monthly_anomalies["Anomalies"]
            .pct_change()
            .replace([float('inf'), float('-inf')], 0)
            .fillna(0) * 100
    )
    
    monthly_anomalies["Month"] = monthly_anomalies["Month"].apply(
        lambda x: pd.Timestamp(year=current_year, month=x, day=1).strftime("%B")
    )

    return monthly_anomalies.to_dict(orient="records")


# In[16]:


def fetch_latest_anomalies(count: int = 28):
    dff['Date'] = pd.to_datetime(dff['Date'])
    sorted_df = dff.sort_values(by="Date", ascending=False)
    latest_data = sorted_df.head(count)
    anomalies = latest_data[["Date", "Open", "Close", "High", "Low","Anomaly"]].to_dict(orient="records")
    for anomaly in anomalies:
        anomaly["Date"] = anomaly["Date"].strftime("%Y-%m-%d")  # Format dates
    return anomalies


# In[17]:


@app.get("/latest_anomalies", response_class=JSONResponse)
async def latest_anomalies(count: int = 28):
    anomalies = fetch_latest_anomalies(count)
    return {"anomalies": anomalies}


# In[18]:


from datetime import datetime

@app.get("/monthly_statistics")
async def monthly_statistics():
    now = datetime.now()
    current_year = now.year
    current_month = now.month
    dff["Date"] = pd.to_datetime(dff["Date"])
    current_month_data = dff[
        (dff["Date"].dt.year == current_year) & (dff["Date"].dt.month == current_month)
    ]
    total_events = len(current_month_data)
    total_anomalies = len(current_month_data[current_month_data["Anomaly"] == 1])

    return {"total_events": total_events, "total_anomalies": total_anomalies}


# In[19]:


def fetch_last_day_statistics():
    try:
        
        dff['Date'] = pd.to_datetime(dff['Date'])
    except Exception as e:
        print("Error processing the 'Date' column:", e)
        raise ValueError("Failed to process the 'Date' column")

    dff = dff.sort_values(by="Date", ascending=False)
    
    last_day_data = dff.iloc[0]
    is_anomaly = bool(last_day_data['Anomaly'] == 1)
    return {
        "date": last_day_data['Date'].strftime('%Y-%m-%d'),
        "open": last_day_data['Open'],
        "close": last_day_data['Close'],
        "high": last_day_data['High'],
        "low": last_day_data['Low'],
        "is_anomaly": is_anomaly
    }


# In[20]:


@app.get("/daily_statistic", response_class=JSONResponse)
async def daily_statistic():
    last_day_data = fetch_last_day_statistics()
    return last_day_data


# In[21]:


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    anomalies_list = fetch_latest_anomalies()
    return templates.TemplateResponse("dashboard.html", {"request": request, "anomalies": anomalies_list})


# In[22]:


def run_fastapi():
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)


# In[ ]:


run_fastapi()
