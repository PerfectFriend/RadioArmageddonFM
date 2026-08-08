#!/usr/bin/env python
"""Generate all remaining workflows: ad, forecast, newsfeed (style-inheriting beds)."""
import sys, argparse, shutil, tempfile, time
sys.path.insert(0, r"C:\Users\yusya\AI-Radio")
from pathlib import Path
from radio_gen import wf_ad, wf_forecast, wf_newsfeed

STYLE = "dark psychedelic full-on trance, 148 bpm"  # current radio block genre

cases = [
    dict(wf="ad", wf_fn=wf_ad,
         voice_text="КриптоИнквизиция Плюс — новая мобильная платформа для цифровых проповедей. "
                    "Безопасность вашего кошелька — наша миссия. Скачивайте сегодня.",
         out=Path(r"C:\Users\yusya\AI-Radio\out\ad_cryptoinq_plus.mp3"), seed=111),
    dict(wf="forecast", wf_fn=wf_forecast,
         voice_text="Прогноз погоды. В Москве сегодня плюс двадцать два, переменная облачность, "
                    "без осадков. Ветер юго-западный, два метра в секунду.",
         out=Path(r"C:\Users\yusya\AI-Radio\out\forecast_moscow.mp3"), seed=222),
    dict(wf="newsfeed", wf_fn=wf_newsfeed,
         voice_text="Новости инквизиции. Цифровая эра ускоряется: принят новый протокол "
                    "верификации душ, индекс криптоэнтузиазма вырос на двенадцать процентов.",
         out=Path(r"C:\Users\yusya\AI-Radio\out\news_digest.mp3"), seed=333),
]

for c in cases:
    args = argparse.Namespace(
        wf=c["wf"], text=None, voice_text=c["voice_text"], prompt=None,
        style=STYLE, bed_volume=0.22, out=c["out"], seed=c["seed"],
        profile=None, keep_tmp=False, tmp=Path(tempfile.mkdtemp(prefix=f"radio-{c['wf']}-")),
    )
    t0 = time.time()
    out = c["wf_fn"](args)
    print(f"=== {c['wf'].upper()} DONE: {out} in {time.time()-t0:.1f}s ===")
    shutil.rmtree(args.tmp, ignore_errors=True)
