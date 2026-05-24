# 崇德館 告別式 + 致意排程（純靜態版 / GitHub Pages）

純靜態版本：**GitHub Actions** 每天 UTC+8 22:00 跑爬蟲產出 `latest.json`，
**GitHub Pages** serve 一個 vanilla HTML/JS 前端，使用者打開網址即時看到資料。

- 無 server、無 Streamlit、無 cron 本機依賴
- 對網站友善：每天只爬 1 次（vs 每訪客觸發爬一次）
- 純 stdlib Python + vanilla JS，0 build step、0 CDN

## 來源（同 funeral_scraper 上游）

- [告別式場次查詢](https://mortuary.taichung.gov.tw/Frontend/Farewell.aspx)
- [停柩室使用情形](https://mortuary.taichung.gov.tw/frontend/CoffinUse.aspx)

ASP.NET WebForms，需 POST + ViewState。

---

## 目錄結構

```
funeral_scraper_purejs/
├── scripts/
│   ├── scraper_core.py        # 抓取/解析/合併核心(同 funeral_scraper/scraper.py 的核心)
│   ├── scrape_to_json.py      # 進入點:呼叫 core,輸出 docs/data/latest.json
│   └── workflow_scrape.yml    # GH Actions workflow 樣板 (搬 repo 時要 mv)
├── docs/                       # GH Pages 由此 folder serve
│   ├── index.html
│   ├── app.js                 # 純 vanilla JS,讀 latest.json 渲染
│   ├── style.css
│   └── data/
│       └── latest.json        # Actions 每天覆寫
├── .gitignore
└── README.md
```

> **與 `funeral_scraper/` 完全無依賴**(已 audit 通過)。可整個 folder 搬到新 repo 當 root 用。

---

## 部署到新 GitHub repo 的步驟

### 1. 建立 repo

```bash
# 假設你的新 repo 叫 funeral-scraper-web
gh repo create funeral-scraper-web --public --clone
cd funeral-scraper-web
```

> ⚠️ **必須是 public repo** — GitHub Pages 免費 tier 不支援 private repo。
> 若要 private,需要 GitHub Pro ($4/月起)。

### 2. 把這個 folder 內容複製到新 repo root

```bash
# 從 chenso-playground 內複製
cp -r /path/to/chenso-playground/publicStuff/funeral_scraper_purejs/* .
cp /path/to/chenso-playground/publicStuff/funeral_scraper_purejs/.gitignore .
```

### 3. 把 workflow 樣板移到 GH 標準位置

```bash
mkdir -p .github/workflows
mv scripts/workflow_scrape.yml .github/workflows/scrape.yml
```

> 為什麼這個檔在 `scripts/` 而不是直接放好? 因為這個 folder 原本在 chenso-playground
> 內,如果直接放 `.github/workflows/scrape.yml`,父 repo 也會把它當有效 workflow,
> 每天自動跑、產生不該有的 commit。

### 4. 開啟 GitHub Pages

```bash
# 推上去
git add .
git commit -m "init: funeral scraper static docs"
git push -u origin main
```

到 repo 設定:

1. **Settings → Pages**
2. Source = **Deploy from a branch**
3. Branch = **main**, folder = **`/docs`**
4. 儲存,等 1-2 分鐘
5. 網址會是 `https://<你的帳號>.github.io/funeral-scraper-web/`

### 5. 手動觸發第一次 scrape

到 **Actions** tab → 左欄選 **scrape** → 右上 **Run workflow** → 選 days (預設 7) → Run。

跑完後 Actions 會自動 commit `docs/data/latest.json` 到 main,GH Pages 會在
幾分鐘內 publish 更新。重新整理你的網址就會看到資料。

### 6. (選用) 確認排程啟動

```bash
# Actions 介面右上應該顯示 "next run: ..."
# 第二天 UTC 14:00 (台北 22:00) 會自動跑
```

---

## 本機開發 / 測試

### 跑一次 scraper

```bash
python scripts/scrape_to_json.py --days 7        # 預設
python scripts/scrape_to_json.py --days 14       # 14 天
python scripts/scrape_to_json.py --out foo.json  # 自訂輸出路徑
```

只需要 Python 3.9+，**沒有 pip 依賴**(stdlib only)。

### 在本機開 docs

```bash
cd docs && python -m http.server 8000
# 瀏覽器開 http://localhost:8000
```

開不需要任何 npm/build。

---

## UI 功能

| Tab | 內容 |
|---|---|
| 📋 全部場次 | 全部告別式 + 致意期間欄位 (完整 14 欄) |
| 📍 北區戶籍 | 只列戶籍含「北區」的場次,北區 filter force on |
| 🗓️ 致意排程 | 「日期 × 亡者」展開的提早致意行程表 |
| 📅 行事曆視圖 | 致意排程的 日 × 時段 pivot 表 |
| 🪦 停柩室原始 | 停柩室矩陣展開後的長表 |

共用 filter:

- 告別式日期 / 禮廳 / 致意說明 (多選)
- 只看戶籍北區 (預設 ✅)
- 關鍵字搜尋 (姓名/戶籍地/致意地點/禮廳)
- 下載當前篩選結果為 CSV (UTF-8 含 BOM,Excel 直接開)

---

## 「致意」三種情境(同 funeral_scraper 上游)

合併邏輯產生 3 種 `致意說明`:

| 情境 | 條件 | 致意期間 | 致意地點 |
|---|---|---|---|
| **A. 公開致意期間** | 名字在停柩室矩陣裡 | 矩陣首日 ~ 告別式前一日 | 對應停柩室號 |
| **B. 告別式直接在停柩室** | 禮廳是「停棺NN號」 | (只列告別式當日) | 同一停柩室 |
| **C. 正式禮廳** | 禮廳是景福廳/懷恩廳等 | 未公開 | (詢家屬) |

---

## 限制 (誠實揭露)

- **不是即時資料**:最舊 24 小時前(下次 cron 跑才更新)
- **沒有家屬姓名 / 聯絡電話**(網站本來就沒揭露)
- **沒有詳細地址**(只到里)
- **正式禮廳的致意期間未公開**(C 情境)
- **stop-coffin 矩陣標示「不公開」的住客**無法與告別式名單匹配
- **Repo 必須 public** (GH Pages 免費 tier 限制)
- **git history 每天 +1 commit** (Actions push `latest.json`);若在意可改成 force-push 到 `data` branch

---

## 對網站友善

- 每天 1 次 cron (台北 22:00),共 8 個 POST (7 個告別式日 + 1 個停柩室)
- 查詢間隔 1.5 秒
- 完整模擬瀏覽器 form 提交 (ViewState + cookie + Referer)

---

## FAQ

**Q: 排程是 GH cron,GitHub 會 100% 準時跑嗎?**
不會。GH Actions 排程有 "best effort" 延遲(尖峰可能晚 30 分鐘以上,週末更明顯)。
若你要保證準時,改用其他排程器(Cloud Scheduler 等)。

**Q: 怎麼立刻刷新資料,不等 22:00?**
到 Actions tab 點 `scrape` workflow → Run workflow。跑完 ~ 1 分鐘。

**Q: 每天 commit 會讓 repo 變肥嗎?**
`latest.json` ~ 100KB,每天差幾百 bytes-幾 KB。git 內部會 compress,一年大概 < 30MB。

**Q: 如何 host 多個館別(東海/大甲/東勢)?**
改 `scripts/scraper_core.py` 的 `UNIT_CODE_CHONGDE` 常數,或者把 `scrape_to_json.py` 改成迴圈跑所有館別 → 輸出多個 JSON 檔。UI 部分要加 selector。

**Q: 我能不能用 cloudflare/netlify 取代 GH Pages?**
能,只要 host 能 serve 靜態檔即可。把 `docs/` 內容上傳就好。Cron 仍用 GH Actions
(或改用該平台的 cron 方案),只要它把 `latest.json` push 到 host 認識的地方。

---

## 上游/沿革

- 此版 fork 自 `chenso-playground/publicStuff/funeral_scraper/`(本機 Streamlit + cron 版)。
- `scraper_core.py` 是 funeral_scraper/scraper.py line 28-399 的 mirror,保留所有
  邏輯與註解(顏色語意、ViewState 處理、致意三情境推導等)。
- 上游若改 schema,要手動把 core 同步過來。
