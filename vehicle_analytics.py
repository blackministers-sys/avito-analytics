"""Vehicle hierarchy extraction and evidence-based segment analysis for Avito exports."""
from __future__ import annotations

import re
import unicodedata
import pandas as pd

MAKE_ALIASES = {
    "lada": ["лада", "ваз", "vaz", "lada"],
    "toyota": ["тойота", "toyota"],
    "nissan": ["ниссан", "nissan"],
    "mitsubishi": ["митсубиси", "мицубиси", "mitsubishi"],
    "honda": ["хонда", "honda"],
    "mazda": ["мазда", "mazda"],
    "ford": ["форд", "ford"],
    "volkswagen": ["фольксваген", "vw", "volkswagen"],
    "hyundai": ["хендай", "хёндай", "hyundai"],
    "kia": ["киа", "kia"],
    "renault": ["рено", "renault"],
    "chevrolet": ["шевроле", "chevrolet"],
    "bmw": ["бмв", "bmw"],
    "mercedes-benz": ["мерседес", "mercedes", "mercedes-benz"],
    "audi": ["ауди", "audi"],
    "opel": ["опель", "opel"],
    "peugeot": ["пежо", "peugeot"],
    "citroen": ["ситроен", "citroen"],
    "subaru": ["субару", "subaru"],
    "suzuki": ["сузуки", "suzuki"],
    "lexus": ["лексус", "lexus"],
    "volvo": ["вольво", "volvo"],
    "skoda": ["шкода", "skoda"],
    "chery": ["чери", "chery"],
    "geely": ["джили", "geely"],
    "great wall": ["грет волл", "great wall"],
    "ssangyong": ["санг енг", "ssangyong"],
    "infiniti": ["инфинити", "infiniti"],
    "land rover": ["ленд ровер", "land rover"],
    "porsche": ["порше", "porsche"],
    "dodge": ["додж", "dodge"],
    "jeep": ["джип", "jeep"],
    "fiat": ["фиат", "fiat"],
    "daewoo": ["дэу", "daewoo"],
    "газ": ["газ"],
    "уаз": ["уаз", "uaz"],
}
MODEL_ALIASES = {
    "lada": {"granta":["гранта","granta"],"kalina":["калина","kalina"],"priora":["приора","priora"],"vesta":["веста","vesta"],"largus":["ларгус","largus"],"niva":["нива","niva","4x4"],"2110":["2110"],"2114":["2114"],"2107":["2107"]},
    "toyota": {"corolla":["corolla","королла"],"camry":["camry","камри"],"rav4":["rav4","рав4","рав 4"],"avensis":["avensis","авенсис"],"land cruiser":["land cruiser","ленд крузер"],"prius":["prius","приус"],"auris":["auris","аурис"],"yaris":["yaris","ярис"],"highlander":["highlander","хайлендер"]},
    "nissan": {"almera":["almera","альмера"],"qashqai":["qashqai","кашкай"],"x-trail":["x-trail","xtrail","икстрейл","х-трейл"],"primera":["primera","примера"],"teana":["teana","теана"],"note":["note","ноут"],"juke":["juke","жук"],"murano":["murano","мурано"],"tiida":["tiida","тиида"]},
    "mitsubishi": {"lancer":["lancer","лансер"],"outlander":["outlander","аутлендер"],"pajero":["pajero","паджеро"],"asx":["asx","асх"],"galant":["galant","галант"],"colt":["colt","кольт"],"l200":["l200","л200"]},
    "honda": {"civic":["civic","сивик"],"accord":["accord","аккорд"],"cr-v":["cr-v","crv","срв"],"fit":["fit","фит"],"stream":["stream","стрим"],"jazz":["jazz","джаз"]},
    "mazda": {"3":["mazda 3","мазда 3"],"6":["mazda 6","мазда 6"],"cx-5":["cx-5","cx5"],"cx-7":["cx-7","cx7"],"demio":["demio","демио"]},
    "ford": {"focus":["focus","фокус"],"mondeo":["mondeo","мондео"],"fiesta":["fiesta","фиеста"],"fusion":["fusion","фьюжн"],"kuga":["kuga","куга"],"transit":["transit","транзит"]},
    "volkswagen": {"polo":["polo","поло"],"golf":["golf","гольф"],"passat":["passat","пассат"],"tiguan":["tiguan","тигуан"],"touareg":["touareg","туарег"],"jetta":["jetta","джетта"]},
    "hyundai": {"solaris":["solaris","солярис"],"elantra":["elantra","элантра"],"accent":["accent","акцент"],"sonata":["sonata","соната"],"ix35":["ix35","ix 35"],"tucson":["tucson","туссан"],"creta":["creta","крета"],"santa fe":["santa fe","санта фе"]},
    "kia": {"rio":["rio","рио"],"ceed":["ceed","сид"],"cerato":["cerato","церато"],"sportage":["sportage","спортейдж"],"sorento":["sorento","соренто"],"optima":["optima","оптима"],"spectra":["spectra","спектра"]},
    "renault": {"logan":["logan","логан"],"sandero":["sandero","сандеро"],"duster":["duster","дастер"],"megane":["megane","меган"],"fluence":["fluence","флюенс"],"kaptur":["kaptur","каптюр"]},
    "chevrolet": {"cruze":["cruze","круз"],"lacetti":["lacetti","лачетти"],"aveo":["aveo","авео"],"niva":["нива","niva"],"captiva":["captiva","каптива"]},
    "bmw": {"3 series":["3 series","3 серия","e46","e90","f30","g20"],"5 series":["5 series","5 серия","e39","e60","f10","g30"],"x5":["x5","х5"],"x3":["x3","х3"]},
    "mercedes-benz": {"c-class":["c-class","c class","c-класс","w203","w204","w205"],"e-class":["e-class","e class","е-класс","w211","w212","w213"],"m-class":["m-class","ml","мл","w164"],"sprinter":["sprinter","спринтер"]},
    "audi": {"a4":["a4","а4"],"a6":["a6","а6"],"q5":["q5"],"q7":["q7"]},
    "opel": {"astra":["astra","астра"],"vectra":["vectra","вектра"],"corsa":["corsa","корса"],"zafira":["zafira","зафира"]},
    "skoda": {"octavia":["octavia","октавия"],"rapid":["rapid","рапид"],"fabia":["fabia","фабия"],"superb":["superb","суперб"]},
}
GENERATION_ALIASES = {
    ("mitsubishi","lancer"): {"9":"IX","9 поколение":"IX","ix":"IX","10":"X","10 поколение":"X","x":"X","8":"VIII","viii":"VIII"},
    ("toyota","corolla"): {"e120":"E120","e150":"E150","e180":"E180","e210":"E210","e110":"E110"},
    ("toyota","camry"): {"v30":"V30","v40":"V40","v50":"V50","v55":"V55","v70":"V70","v20":"V20"},
    ("nissan","almera"): {"n16":"N16","g15":"G15","classic":"N16"},
    ("nissan","qashqai"): {"j10":"J10","j11":"J11","j12":"J12"},
    ("nissan","x-trail"): {"t30":"T30","t31":"T31","t32":"T32","t33":"T33"},
    ("mitsubishi","outlander"): {"1":"I","2":"II","3":"III","xl":"XL","cw":"CW","gf":"GF"},
    ("honda","civic"): {"7":"VII","8":"VIII","9":"IX","10":"X","fd":"FD","fk":"FK"},
    ("mazda","3"): {"bk":"BK","bl":"BL","bm":"BM","bn":"BN","bp":"BP"},
    ("mazda","6"): {"gg":"GG","gh":"GH","gj":"GJ","gl":"GL"},
    ("ford","focus"): {"1":"I","2":"II","3":"III","4":"IV","mk1":"I","mk2":"II","mk3":"III","mk4":"IV"},
    ("volkswagen","golf"): {"4":"IV","5":"V","6":"VI","7":"VII","8":"VIII","mk4":"IV","mk5":"V","mk6":"VI","mk7":"VII"},
    ("kia","rio"): {"2":"II","3":"III","4":"IV","qb":"QB","fb":"FB","dc":"DC"},
    ("hyundai","solaris"): {"1":"I","2":"II","hc":"HC"},
}
STRUCTURED = {
    "make": ["Марка", "Марка автомобиля", "Марка авто", "Бренд автомобиля"],
    "model": ["Модель", "Модель автомобиля", "Модель авто"],
    "generation": ["Поколение", "Поколение автомобиля", "Кузов", "Код кузова"],
}
def _norm(value):
    value = unicodedata.normalize("NFKC", str(value or "")).casefold().replace("ё","е")
    return re.sub(r"[^a-zа-я0-9]+", " ", value).strip()

def _find_structured(row, names):
    for name in names:
        value = row.get(name, "")
        if pd.notna(value) and str(value).strip() and str(value).strip().casefold() not in {"nan","none"}:
            return str(value).strip()
    return ""

def _contains_alias(text, alias):
    pattern = r"(?<![a-zа-я0-9])" + re.escape(alias).replace(r"\ ", r"\s+") + r"(?![a-zа-я0-9])"
    return re.search(pattern, text, flags=re.I) is not None

def identify_vehicle(row):
    """Prefer explicit columns; otherwise parse title/parameter conservatively."""
    title = " ".join(str(row.get(k, "") or "") for k in (
        "Название объявления", "Параметр", "Подкатегория", "Категория"
    ))
    normalized = _norm(title)
    make_raw = _find_structured(row, STRUCTURED["make"])
    model_raw = _find_structured(row, STRUCTURED["model"])
    generation_raw = _find_structured(row, STRUCTURED["generation"])
    make = _norm(make_raw) if make_raw else ""
    model = _norm(model_raw) if model_raw else ""
    generation = generation_raw.strip().upper() if generation_raw else ""

    if make_raw:
        for canonical, aliases in MAKE_ALIASES.items():
            if make == _norm(canonical) or any(make == _norm(alias) for alias in aliases):
                make = canonical
                break
    if not make:
        matches = []
        for canonical, aliases in MAKE_ALIASES.items():
            for alias in aliases:
                if _contains_alias(normalized, _norm(alias)):
                    matches.append((len(_norm(alias)), canonical))
        if matches:
            make = sorted(matches, reverse=True)[0][1]
    if make and model_raw:
        for candidate, aliases in MODEL_ALIASES.get(make, {}).items():
            if model == _norm(candidate) or any(model == _norm(alias) for alias in aliases):
                model = candidate
                break
    if make and not model:
        for candidate, aliases in MODEL_ALIASES.get(make, {}).items():
            if any(_contains_alias(normalized, _norm(alias)) for alias in aliases):
                model = candidate
                break
    if not make or not model:
        return ("Не определена", "Не определена", "Не определено", "low")

    if not generation:
        candidates = GENERATION_ALIASES.get((make, model), {})
        for alias, canonical in sorted(candidates.items(), key=lambda x: len(x[0]), reverse=True):
            if _contains_alias(normalized, _norm(alias)):
                generation = canonical
                break
        if not generation:
            # Generic chassis codes are accepted only when a structured vehicle has
            # already been recognized; arbitrary numbers are not treated as generations.
            code = re.search(r"\b([a-z]{1,2}\d{2,3}|[a-z]{1,2}\d{1,2})\b", normalized)
            if code:
                generation = code.group(1).upper()
    confidence = "high" if make_raw and model_raw else ("medium" if generation else "low")
    if generation_raw:
        confidence = "high"
    return (make, model, generation or "Не определено", confidence)

def analyze_vehicle_groups(frame: pd.DataFrame) -> dict:
    """Aggregate by make/model/generation and expose sample strength and diagnostics."""
    if frame is None or frame.empty:
        return {"groups": [], "coverage": {"rows": 0, "identified": 0, "share": 0.0}, "insights": []}
    data = frame.copy()
    parsed = data.apply(lambda row: identify_vehicle(row), axis=1, result_type="expand")
    parsed.columns = ["Марка авто", "Модель авто", "Поколение авто", "Уверенность распознавания"]
    data = pd.concat([data.reset_index(drop=True), parsed.reset_index(drop=True)], axis=1)
    data["Показы"] = pd.to_numeric(data.get("Показы", 0), errors="coerce").fillna(0)
    data["Просмотры"] = pd.to_numeric(data.get("Просмотры", 0), errors="coerce").fillna(0)
    data["Контакты"] = pd.to_numeric(data.get("Контакты", 0), errors="coerce").fillna(0)
    data["Расходы"] = pd.to_numeric(data.get("Расходы", 0), errors="coerce").fillna(0)
    data["Город"] = data.get("Город", pd.Series([""] * len(data))).fillna("").astype(str)
    data["Категория"] = data.get("Категория", pd.Series([""] * len(data))).fillna("").astype(str)
    grouped = data.groupby(["Марка авто","Модель авто","Поколение авто"], dropna=False)
    output = []
    for (make, model, generation), group in grouped:
        views = float(group["Просмотры"].sum())
        contacts = float(group["Контакты"].sum())
        spend = float(group["Расходы"].sum())
        ads = int(len(group))
        cpa = spend / contacts if contacts else None
        confidence = group["Уверенность распознавания"].value_counts().index[0]
        cities = int(group["Город"].replace("", pd.NA).nunique())
        categories = int(group["Категория"].replace("", pd.NA).nunique())
        output.append({
            "make": make, "model": model, "generation": generation,
            "ads": ads, "shows": float(group["Показы"].sum()), "views": views,
            "contacts": contacts, "spend": spend, "ctr": float(group["Просмотры"].sum() / group["Показы"].sum()) if group["Показы"].sum() else 0.0,
            "cr": contacts / views if views else 0.0, "cpa": cpa,
            "no_contact_ads": int((group["Контакты"] == 0).sum()),
            "cities": cities, "categories": categories, "confidence": confidence,
            "status": "Не определена" if make == "Не определена" else ("Есть контакты" if contacts else "Нет контактов"),
            "city_breakdown": group.groupby("Город", dropna=False).agg(ads=("Город","size"), views=("Просмотры","sum"), contacts=("Контакты","sum"), spend=("Расходы","sum")).reset_index().to_dict("records"),
        })
    output.sort(key=lambda x: (-x["contacts"], x["cpa"] if x["cpa"] is not None else float("inf"), -x["views"]))
    identified = data["Марка авто"].ne("Не определена")
    coverage = {"rows": int(len(data)), "identified": int(identified.sum()),
                "share": float(identified.mean() * 100) if len(data) else 0.0,
                "generation_known": int(data["Поколение авто"].ne("Не определено").sum())}
    insights = []
    valid = [g for g in output if g["make"] != "Не определена" and g["ads"] >= 3]
    scalable = [g for g in valid if g["contacts"] >= 5 and g["cpa"] is not None]
    if scalable:
        best = sorted(scalable, key=lambda x: (x["cpa"], -x["contacts"]))[0]
        insights.append({"kind":"good","title":f"Самый дешёвый подтверждённый сегмент: {best['make']} {best['model']} {best['generation']}",
                         "text":f"{best['contacts']:.0f} контактов на {best['ads']} объявлениях; CPA {best['cpa']:.2f} ₽. Это кандидат для проверки масштабирования, не доказательство причинного эффекта."})
    zero = [g for g in valid if g["views"] >= 100 and g["spend"] > 0 and g["contacts"] == 0]
    if zero:
        worst = sorted(zero, key=lambda x: -x["spend"])[0]
        insights.append({"kind":"bad","title":f"Расходы без контактов: {worst['make']} {worst['model']} {worst['generation']}",
                         "text":f"{worst['ads']} объявлений, {worst['views']:.0f} просмотров и {worst['spend']:.2f} ₽ расходов. Нужна проверка карточек и качества трафика."})
    if not insights:
        insights.append({"kind":"warn","title":"Пока нет устойчивого автомобильного лидера",
                         "text":"Для уверенного вывода нужны повторяющиеся объявления и достаточное число контактов в каждой группе. Сначала проверьте покрытие распознавания."})
    return {"groups": output, "coverage": coverage, "insights": insights}
