# 電影場次 — 已定案產品架構與 UI/UX 契約（2026-10-08）

> **狀態：產品負責人已決定；預設凍結（LOCKED）。**
> **專案：** `DandaDany/anime_movie_screening`  
> **正式網站：** https://dandadany.github.io/anime_movie_screening/  
> **範圍：** 現行產品與發佈架構、資料契約、使用者旅程、桌機／手機互動、品牌與 SEO、Agent 修改驗收。  
> **目的：** 防止後續 Agent 在修 SEO、圖片、爬蟲或局部功能時，擅自把介面回退到已否決的舊版。

## 0. 決策優先順序和版本辨識

1. **當次使用者明確決定 > 本文件最近已確認的規則 > 實際最新 `main` 與已通過的回歸測試 > 舊 `DECISIONS.md`／README > 先前 PR 或 Agent 建議。**
2. 若文件與實際 `main` 不一致：先釐清「bug／待實作」或「新決策」，**不得因為舊文件或舊 PR 就自行回退**。將差異報告使用者，確認後修改文件、程式與測試。
3. 以最新 `main` 為修改基準，不使用被否決的改版分支作起點。最新已確認的 UI 修正是 **PR #105（恢復原版海報上浮互動、橫圖置中、未上映頁深色背景）**、**PR #106（移除海報 hover 白框）**；**PR #91 的整體 UI 重設計被否決**。歷史參考可以讀，但不能整套覆蓋回去。
4. **本文件是「使用者已核定的狀態」，不是 UI redesign brief。** 無明確授權不得用個人美學或框架便利性更換資訊架構。

## 1. 產品核心與唯一主旅程（LOCKED）

產品回答的問題是：

> **「今天想看什麼動畫電影，可以去哪裡看？」**

流程固定：**首頁選電影 → 電影專屬頁 → 選日期／縣市／版本／影城／時間 → 查影城與場次 → 地圖／影城詳情與官方訂票。**

- 首頁優先展示 **正在上映**、**即將上映** 的電影海報，屬 **Poster-first 電影選擇頁**，不是全台影城目錄。
- **不要**把首頁改為影城排行榜／影城搜尋首頁；**不要**把「今天這家影城有什麼」當成主要資訊架構。
- 每部電影具有固定可分享的 `movie-<id>.html` URL，不能把所有電影重新折回只有首頁 query-string 的單頁工具。
- 現在**不規劃**獨立縣市頁／影城 SEO landing page。SEO 與 AI 搜尋優先圍繞「今日有什麼電影」及「某電影在某城市、某影城、某時刻上映」。
- 即將上映且尚無實際場次的電影應有可讀的獨立頁，**不能跳到另一部電影**。已經上映過但下檔的片保留可索引的存檔 URL；未上映且停用的草稿不公開。

## 2. 現行技術架構（LOCKED，除非另行核定遷移）

| 層 | 權威實作／用途 |
| --- | --- |
| 前端 | `web/` 的原生 HTML／CSS／JavaScript，**Leaflet** 地圖；GitHub Pages 靜態發布 |
| 地圖與篩選 | `web/app.js`、`web/styles.css`、`web/date-state.js`、`web/time-filter.js`、`web/version-filter.js` |
| 電影選擇首頁 | `web/index.html`、`web/discovery.js`、`web/discovery.css` |
| 電影獨立頁與影城列表 | `scripts/build_seo_pages.py` 建置時產生 `web/movie-<id>.html`，配合 `web/movie-detail-list.js`、`web/movie-detail-list.css` |
| 公開地圖資料契約 | `web/data/locations.geojson`；電影 → 日期 → 影城 Features／showtimes |
| 選片資料 | `web/data/movie_discovery.json`（片名、別名、上映日、海報、fit 等）；追蹤源為 `data/control/tracked_movies.json` 等既定流程 |
| Logo | 影城 Logo 在 `web/assets/logos/`；本站品牌素材在 `web/assets/brand/` |
| 爬蟲和匯出 | `scripts/` Python；SQLite 為執行期工作資料，不是網站公開 API |
| 控制面 | 原有 Django／Render 後台、影城主檔與追蹤片單控制面；保持既定備援及來源政策 |
| 排程／發布 | GitHub Actions → `web/data` → GitHub Pages；建置時生成 SEO HTML、sitemap、robots，並通知 IndexNow |
| 量測／搜尋工具 | GA4、Search Console、sitemap、robots、JSON-LD、IndexNow |

**不要**只因為加入 UI 功能就擅自引入 React／Next.js、改為 SSR、換地圖庫、遷移主資料庫，或讓瀏覽器直接抓影城官網。這些均須另提遷移設計並取得授權。

### 資料與更新時序

1. `daily-crawl.yml`：**台灣時間每日 06:00** deterministic full crawl；依原有官方來源優先、經驗證的備援與品質檢查匯出資料。
2. **07:00 ChatGPT 網路補漏／研究排程**：負責驗證 crawler 難取得的公開場次，把可審計的小型紀錄寫入 `data/control/web_research_supplement.json`。這是獨立的外部排程；**不要假稱 GitHub cron 自動啟動 AI**。
3. `supplemental-0600.yml`：當補漏 control 檔提交到 main 後，驗證來源政策，合併補漏資料、deterministic fallback、麻豆等既有備援，重建公開 GeoJSON。
4. **`map-data-writer`** 共用寫入鎖 `cancel-in-progress: false`，不可讓爬蟲與補漏相互取消或並行覆寫。
5. 各 Pages deploy 使用 `pages` 同組 **`cancel-in-progress: true`**，讓最新站點版本取代舊排隊任務。部署流程須同時生成 SEO 頁和 sitemap。
6. workflow 綠燈不代表每個影城來源都正確；需要來源層級對照與真實場次驗證。補漏不能用臆測時間；不能不經測試改掉來源選擇、場次／電影比對及版本規則。
7. 所有時間以 **Asia/Taipei** 解釋；台灣今天仍可看的場次會隨時間推進減少。切換日期時，顯示該日期的場次，不應把今天的過期限制錯套到未來日期。

### Showtimes 單一真實來源

- `visibleShowtimes()`／已選日期、縣市、版本、時間、影城與其他既定 filter state 決定各場次是否可見。
- 地圖 Logo 場次 badge 與大小、popup、篩選數量、搜尋結果、影城清單及摘要不可各算各的，需與**當下相同 filter state** 一致；零場次的未選項目通常不應繼續出現在篩選可選值。
- 當前時間 AUTO，依台北目前分鐘，已開始的場次（時間 <= 現在）不當成「現在仍可看」；MANUAL slider 保留目前既定邏輯和 quick periods。移動日期須重新檢查該日期可見值。
- 場次資料的 `movie_features_by_date`、名稱 aliases、原有 booking/source metadata 是前端／SEO／補漏共同契約。更動欄位必須同步審查 Python export、JS、SEO generator、fixtures。
- 未識別或無標記的版本標籤在現有篩選語意中 fallback 為 **「數位」**；不得因小修順便改動。

## 3. 視覺與操作不變條款

### A. 首頁：Poster-first（LOCKED）

- 首屏是**正在上映／即將上映** 兩區的電影 Poster 網格；保留深色、略帶透明感的電影氛圍，不變成影城清單或另一套操作面板。
- 原本**首頁不放品牌 Logo 圖**：維持可見的「電影場次」文字和「快速找到想看的動畫電影」。Logo 圖只用於 favicon、裝置 icon、結構化資料等；沒有新授權不得插回首頁。
- **所有 Poster 卡的外框統一 2:3**，在桌機／手機格線中一樣大。海報容器 `.movie-card__poster` 是 `span`，**必須 `display: block`** 才能正確套用寬高比例和 transform。
- 直式圖 `object-fit: cover`；橫式／特殊比例圖由 `poster_fit: contain` 指示，使用 `object-fit: contain` + 水平、垂直置中，**不能改成 cover 硬裁掉橫圖**；畫布／卡片比例不變。
- 文字**完整顯示**、字體可讀，不得偷偷恢復 2-line clamp 或造成下一排海報蓋住長片名。最近已調整片名為桌機約 15.5px、手機約 14px。
- 桌機有滑鼠的狀態，沿用**歷史已確認的整張電影卡 hover**：`translateY(-8px) scale(1.04)`，卡片浮起、陰影加強；不推動隔壁卡片。**懸浮時不要白色框線**，不要誤改為只有 poster 元素 `scale(...)` 取代原本的 lift。
- 觸控手機沒有 hover，不得強制加入永久放大；鍵盤聚焦須仍可辨識（可以使用陰影／其他可及性標示，但不要恢復使用者否決的白色邊框）。
- 首頁底部保留低干擾的資料更新註記、真實 `locations.geojson.updated_at` 更新時間與「資料來源與更新方式」連結。

### B. 電影獨立頁：桌機（LOCKED）

- 三欄順序：**原版篩選 Sidebar（左）→ Compact 影城列表（中）→ 原版 Leaflet 地圖（右）**。不是新版分割式 dashboard，也不可改成影城目錄首頁。
- 影城列表保留短卡，約 **68px 高**，僅呈現**影城名稱 + 縣市淡橘色 pill + 可見場次時間**。不直接放距離、品牌介紹、地址、訂票 CTA。
- 影城列表標題為 **「影城列表」**，**旁邊不要顯示總數（例如「50」）**。
- 縣市 pill 使用與 popup「N 場」相同設計語言：柔和淡橘底／深橘文字／圓角膠囊；**不出現「#」**。城市取該 feature `properties.city`；資料缺失時不捏造。
- 影城距離可作內部最近優先排序／data attribute，但不在列表顯示數值；點卡片要連動定位影城和開啟既有 popup。
- **原版 popup 是完整詳情與行動入口**：地址、場次、版本、官方來源／售票或座位入口等保留，不能搬進列表或取消原本功能。

### C. 電影獨立頁：手機（LOCKED）

- 仍以原版**Leaflet 地圖 + 40dvh resting 篩選底部抽屜**為基礎（約地圖 60%、抽屜 40%）；保留拖拉展開及原有搜尋、日期、篩選狀態。
- 電影頁的影城列表在手機變為**地圖上、底部抽屜上方的橫向卡片 carousel**；不是桌機三欄縮小版。影城卡同樣維持短卡、縣市 pill、時間資訊。
- Popup / Bottom Sheet 點影城、點地圖、Home／重置、搜尋結果與日期改變的互動，沿用最新主線行為；不可因一般美化把原版 Leaflet 操作撤換。
- Home 地圖控制與 Leaflet +/- 已統一在同一組控制位置；不回退至舊版散落的 Home 按鈕或將 Home 改成只關 popup。選擇另一部電影時導往其獨立 canonical 電影頁。
- 桌機／手機需要**各自驗證**；桌機測試通過，不代表手機 UX 通過。

### D. 無場次／未上映頁（LOCKED）

- 即將上映的電影尚無日期／影城／場次資料時，保留該電影 canonical landing page，顯示片名、海報（若有）、預定上映日期及「目前沒有可查詢場次」。
- 此類頁面使用**與選片首頁同系列的半透明黑色漸層背景、白／淺灰文字、清楚的返回首頁入口**，不是早期白／灰淺色背景。
- 已下檔 archive 頁屬另一種狀態，保留索引及歷史 URL；**不可將「未上映但無場次」與「已下檔」混成同一文案或自動跳首頁**。

## 4. 搜尋、分享與品牌（LOCKED）

- 首頁 `title`／`description`、OG／Twitter metadata 和電影頁 metadata **分開管理**；更換分享文案不應同步亂改首頁可見標題／Tagline。**社群分享文案仍可另行決定；不要把 Agent 提案當作已核定文字**。
- 使用者已指定的方形 Logo 為品牌來源；首頁畫面不直接顯示。favicon／Apple icon／Organization JSON-LD 可以使用此圖的合適處理版本。**透明背景 Logo**已提出需求；轉換與置換須驗證圖檔內容（不是只有改 URL）。
- 使用者已提供首頁 OG 圖（原圖米色系，文字「這部哪裡還有上映？／漫迷的電影查詢首選」），以**1200×630、40:21、約 1.91:1** 分享卡為目標。不得替換成 AI 生成的另一張未核定圖片。
- 主頁公開 JSON-LD 表示**今天可看的動畫電影**（movie-first ItemList），電影頁表示 `Movie`、`City`、`MovieTheater`、`ScreeningEvent`、實際場次時間及可用官方來源；不可編造場次或把已結束時段當「現在尚可購票」。
- SEO builder `scripts/build_seo_pages.py` 在每次部署生成靜態可爬 HTML、canonical、robots、sitemap；`OAI-SearchBot`／`PerplexityBot`／Google／Bing 規則與 IndexNow 都屬既有流程。
- **分享預覽是否顯圖須實際驗證不同平台的抓取與快取**；`og:image` 標籤存在或 CI 成功，不能證明平台實際顯示圖片。
- 來源說明 `web/about.html` 和品牌 404 已上線；關於聯絡／合作入口目前只有建議，**尚未取得使用者聯絡內容／確定加入，不得憑空新增姓名、Email、社群帳號**。
- 不主動新增獨立影城入口／自訂網域／PWA 大改版；如需進入 roadmap，先與使用者討論並確認。

## 5. Agent 修改 SOP（強制）

### 開始前

1. GitHub 讀寫**一律使用已連線 GitHub App**，不得用 `gh` CLI 繞過；不要跑 Codex 或消耗使用者 Codex 配額。
2. 讀最新 `main`、本文件、`DECISIONS.md` 和相關程式、測試與最近 PR，記錄本次功能涉及的 LOCKED 區塊。
3. 將需求分類：錯誤修復、局部改善、功能／資料變更、架構重設。**沒有明確授權不做架構／UI 重設計。**
4. 有現成已驗收的互動失效時，**先找實際有效的歷史 PR／CSS／JS，找根因再修**。不准猜一個 `scale` 值就回報「已修好」。

### 修改範圍

5. 從最新 `main` 建工作分支及 PR。修改必要的最小檔案；避免動 crawler/GeoJSON/日期演算法／底部抽屜／popup 等不相關範圍。
6. 修改電影列表需同步考慮 **build-time 靜態 HTML** 與 JS hydration 後畫面；兩者必須一致。
7. 修改首頁 Poster：不可讓修正比例破壞 hover，也不可讓新增陰影恢復白框；檢查 `display`、`aspect-ratio`、`object-fit`、`object-position`、hover transform、focus、長片名。
8. 修改資料與排程：完整檢查 source policy、場次日界線、filter count、寫入競爭鎖、產物 SEO。
9. 重大變更需先清楚列出產品取捨、兼容策略、rollback 方案並取得同意；已核定介面不能因「比較好看」或「比較適合 SEO」自行換掉。

### 驗收與發布

10. **至少跑**既有 SEO acceptance、Poster runtime、桌機／手機 browser regression，若碰時間、篩選、爬蟲則加對應測試；不得隱瞞失敗／skip。
11. 對視覺 bug 使用真正瀏覽器截圖與前後比較，**不是只看 CSS 值**；必要時檢查 DOM 實際盒尺寸、可見性、游標 hover 效果、文字／圖片溢位。
12. 針對本文件 LOCKED 項目增加/保留回歸斷言：卡片尺寸、橫圖置中、hover 浮起且沒有白框、列表無數字、有縣市 pill、桌機三欄、手機底部抽屜、URL 路由、未上映頁深色背景。
13. 當次 PR **通過檢查後才合併**。合併不等於上線：另外確認 Pages deploy 成功；如涉及分享圖，驗證檔案可取得及社群實際預覽。
14. 每個完成報告都要分開寫明「已提交」「測試通過」「已合併」「部署成功」「已於公開頁實際驗證」；不得混用這些狀態。
15. **要改 LOCKED 規則必須由使用者明確確認**，並於同一 PR 更新本文件、測試與變更原因；不可默默覆寫或沿用前一個 Agent 的未核定方案。

## 6. 既有 PR 與回歸定位

| 參考 | 意義 |
| --- | --- |
| PR #91 | **已否決**的整體介面重設計，不可復用為新主頁模板 |
| PR #92–96 | 恢復原版地圖／三欄影城清單／手機卡片與 Poster-first 選片等既有行為 |
| PR #97–100 | 現行 SEO/AI 搜尋機器可讀語意，盡量不影響可見 UI |
| PR #101 | Pages 最新部署優先、保留資料 writer 防衝突規則 |
| PR #102 | 首頁底部更新來源小字、About 和 404 |
| PR #103–104 | 品牌 meta／分享、影城縣市膠囊、海報比例與 hover 修正歷程（**中途回歸問題不可照搬**） |
| PR #105 | **可用參考**：恢復早期整張卡的 hover、讓 Poster `display:block`、未上映頁深色 |
| PR #106 | **可用參考**：hover 保留陰影但移除白色框線 |

> **提醒**：上表是定位入口，不代表只看 PR 標題就能確認實作。應以最新 `main` 的程式、實測和使用者本次回饋為準。

## 7. 現行待確認／不應推定成已完成

- 透明背景 Logo：**提出修改需求，不等於已將網站素材替換成透明版**。
- 社群 OG 預覽缺圖：目前有 `og:image` 與站內素材，但某個分享平台截圖顯示預設圖，**實際平台抓圖／快取原因待查**。
- 分享標題、說明的新文案：已提出建議，**仍需使用者核定**。
- 聯絡資料／合作入口：已討論，**尚未新增**。
- 第三方平台抓取或 Google 收錄／AI 排名，不以 workflow 成功視為保證。

---

**給下一位 Agent 的一句話：**

> 在「電影場次」，維護的不是你自己想像中的電影網站，而是使用者已確認的 **Poster-first 選片 → 電影專屬頁 → 原版 Sidebar + Compact 影城列表 + Leaflet 地圖**；任何 SEO、品牌、小功能、資料補漏都必須先保護這條路徑，以及手機地圖＋40dvh 抽屜和已確認的互動細節。
