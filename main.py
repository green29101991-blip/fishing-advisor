from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timedelta
import requests
import ephem

app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="templates"), name="static")

WEATHER_API_KEY = "e452f467896c49b4912130415252909"

def degrees_to_direction(deg):
    if deg is None:
        return "–", "•"
    directions = [
        ("С", "↑"),
        ("СВ", "↗"),
        ("В", "→"),
        ("ЮВ", "↘"),
        ("Ю", "↓"),
        ("ЮЗ", "↙"),
        ("З", "←"),
        ("СЗ", "↖")
    ]
    index = round(deg / 45) % 8
    return directions[index]

def get_weather(city: str = "Moscow", days: int = 14):
    url = f"http://api.weatherapi.com/v1/forecast.json?key={WEATHER_API_KEY}&q={city}&days={days}&lang=ru"
    response = requests.get(url)
    if response.status_code != 200:
        raise HTTPException(status_code=400, detail="Ошибка при получении погоды")
    return response.json()

def get_moon_phase(date: str):
    moon = ephem.Moon(date)
    phase = moon.moon_phase * 100
    if phase < 5 or phase > 95:
        return "🌑 Новолуние"
    elif 5 <= phase < 45:
        return "🌒 Растущая Луна"
    elif 45 <= phase <= 55:
        return "🌕 Полнолуние"
    else:
        return "🌖 Убывающая Луна"

def get_advice_text(score: int):
    if score >= 9:
        return "🌟 Идеальный клёв! Ехать обязательно!"
    elif score >= 7:
        return "🎣 Отличный клёв. Шансы очень высоки!"
    elif score >= 5:
        return "🐟 Средний клёв. Можно попробовать."
    elif score >= 3:
        return "⚠ Слабый клёв. Мало шансов."
    else:
        return "🚫 Плохой клёв. Лучше остаться дома."

def generate_daily_advice(weather_data, date: str):
    moon_phase = get_moon_phase(date)

    periods = {
        "morning": {"hours": range(6, 12), "name": "🌅 Утро (6:00–12:00)", "data": []},
        "day": {"hours": range(12, 18), "name": "☀ День (12:00–18:00)", "data": []},
        "evening": {"hours": range(18, 24), "name": "🌇 Вечер (18:00–24:00)", "data": []},
        "night": {"hours": list(range(0, 6)), "name": "🌙 Ночь (0:00–6:00)", "data": []}
    }

    target_day = None
    for day in weather_data["forecast"]["forecastday"]:
        if day["date"] == date:
            target_day = day
            break

    if not target_day:
        target_day = weather_data["forecast"]["forecastday"][0]

    for hour_data in target_day["hour"]:
        hour = int(hour_data["time"].split()[1].split(":")[0])
        for period in periods.values():
            if hour in period["hours"]:
                period["data"].append(hour_data)
                break

    advice_blocks = []
    for period in periods.values():
        if not period["data"]:
            continue

        temps = [h["temp_c"] for h in period["data"]]
        winds = [h["wind_kph"] / 3.6 for h in period["data"]]
        wind_dirs = [h["wind_degree"] for h in period["data"]]
        rains = [h["precip_mm"] for h in period["data"]]
        humidities = [h["humidity"] for h in period["data"]]
        pressures_hpa = [h["pressure_mb"] for h in period["data"]]

        avg_temp = sum(temps) / len(temps)
        avg_wind = sum(winds) / len(winds)
        avg_wind_dir_label, avg_wind_dir_arrow = degrees_to_direction(sum(wind_dirs) / len(wind_dirs))
        total_rain = sum(rains)
        avg_humidity = sum(humidities) / len(humidities)
        avg_pressure_hpa = sum(pressures_hpa) / len(pressures_hpa)
        avg_pressure_mmhg = avg_pressure_hpa * 0.750062

        score = 0
        if moon_phase in ["🌒 Растущая Луна", "🌕 Полнолуние"]:
            score += 3
        elif moon_phase == "🌑 Новолуние":
            score += 0
        else:
            score += 1

        if 15 <= avg_temp <= 25:
            score += 2
        elif 10 <= avg_temp < 15 or 25 < avg_temp <= 30:
            score += 1

        if avg_wind <= 3:
            score += 2
        elif 3 < avg_wind <= 5:
            score += 1

        if avg_wind_dir_label in ["Ю", "ЮЗ", "З"]:
            score += 1

        if total_rain == 0:
            score += 2
        elif total_rain < 2:
            score += 1

        if 40 <= avg_humidity <= 70:
            score += 1

        if 750 <= avg_pressure_mmhg <= 770:
            score += 2
        elif 740 <= avg_pressure_mmhg < 750 or 770 < avg_pressure_mmhg <= 780:
            score += 1

        score = min(max(int(score), 0), 10)

        advice_blocks.append({
            "period": period["name"],
            "moon_phase": moon_phase,
            "temp": f"{avg_temp:.1f}°C",
            "wind": f"{avg_wind:.1f} м/с",
            "wind_direction_label": avg_wind_dir_label,
            "wind_direction_arrow": avg_wind_dir_arrow,
            "rain": f"{total_rain:.1f} мм",
            "humidity": f"{avg_humidity:.0f}%",
            "pressure_value": avg_pressure_mmhg,
            "pressure": f"{avg_pressure_mmhg:.0f} мм рт. ст.",
            "score": score,
            "advice": get_advice_text(score)
        })

    return advice_blocks

@app.get("/")
def read_root(request: Request, date: str = None, city: str = "Moscow"):
    today = datetime.now().date()
    max_date = today + timedelta(days=14)
    today_str = today.strftime("%Y-%m-%d")
    max_date_str = max_date.strftime("%Y-%m-%d")

    if not date:
        date = today_str
    else:
        try:
            selected = datetime.strptime(date, "%Y-%m-%d").date()
            if selected > max_date:
                date = max_date_str
            elif selected < today:
                date = today_str
        except:
            date = today_str

    try:
        weather = get_weather(city=city, days=14)
        advice_blocks = generate_daily_advice(weather, date)
        avg_score = sum(block["score"] for block in advice_blocks) / len(advice_blocks)
        summary_advice = get_advice_text(int(avg_score))
        
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "advice_blocks": advice_blocks,
                "date": date,
                "city": city,
                "avg_score": avg_score,
                "summary_advice": summary_advice,
                "today": today_str,
                "max_date": max_date_str,
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))