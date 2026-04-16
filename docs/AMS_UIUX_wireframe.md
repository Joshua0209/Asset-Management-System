這是基於 `ams-prototype-v2.html` 原始碼所整理出的 UI/UX Wireframe Flow 範例，以下轉化為開發者視角的規格文件，包含全域狀態、各頁面佈局與互動邏輯。

---

# UI/UX Wireframe Flow: AssetCore AMS (資產管理系統)

## 全域資料狀態 (Global State / API Entities)
- **UserSession**: `{ name: string, role: 'Manager' | 'Holder', department: string }`
- **Assets**: 陣列，包含物件 `{ id: string, name: string, category: string, status: 'InUse' | 'Repair' | 'Review' | 'Disposed', holder: string, price: number, version: number }`
- **RepairRequests**: 陣列，包含物件 `{ reqId: string, assetId: string, applicant: string, priority: 'High' | 'Mid' | 'Low', step: number }`

---

## View 1: Manager Dashboard (管理員儀表板)

**[UI 佈局與元件]**
- **Sidebar (全域):** 包含 Logo、導航選單 (儀表板、資產清單、申請審查、維修工單) 及使用者資訊。
- **KPI Row:** 四個數據卡片顯示「總資產、使用中、維修中、待審查」數量與進度條。
- **Main Content:**
  - **Bar Chart:** 顯示資產類別分布（筆電、桌機、螢幕等）。
  - **Work Order Summary:** 網格小卡顯示今日新增、待處理、進行中、已完成工單數。
  - **Review Table:** 顯示最近 3 筆待審查申請單號與申請人。
  - **Announcements:** 垂直排列的系統公告清單。

**[使用者互動 Flow]**
1. 點擊 `[資產清單]` -> 導航至 **View 2 (Asset List)**。
2. 點擊 `Review Table` 項目 -> 導航至 **View 4 (Review Screen)**。
3. 點擊 `[登出]` -> 清除 Session 並導航至 **Login Screen**。

---

## View 2: Asset List (資產管理列表)

**[UI 佈局與元件]**
- **TopBar:** - 麵包屑導航。
  - Button Group: `[批次上傳]`, `[匯出報告]`, `[+ 新增資產]`。
- **Filter Bar:** 包含關鍵字搜尋框與類別快速篩選標籤 (Tag)。
- **Asset Table:** - 多選 Checkbox。
  - 欄位：資產 ID (Mono 字體)、名稱、類別、部門、狀態標籤 (Badge)、最後更新日期。
  - 操作：`[詳情]` 按鈕。
- **Pagination:** 顯示總筆數與分頁切換按鈕。

**[使用者互動 Flow]**
1. 點擊 `[+ 新增資產]` -> 彈出 **Modal (Add Asset)**。
2. 點擊表格內 `[詳情]` -> 導航至 **View 3 (Asset Detail)**。
3. 勾選多個項目 -> 顯示「批量操作選單」（批量核准、報廢）。

---

## View 3: Asset Detail (資產詳情頁)

**[UI 佈局與元件]**
- **Header Info:** 顯示資產名稱與唯一 ID，右側顯示狀態 Badge。
- **Action Bar:** 包含 `[編輯資產]`, `[指派使用者]`, `[維修申請]`, `[報廢資產]`。
- **Grid Content:**
  - **Basic Info:** 兩欄式佈局顯示序號 S/N、金額、保固日期、當前使用者等。
  - **Timeline:** 垂直時間軸顯示該資產的異動紀錄 (建立、送修、指派)。

**[使用者互動 Flow]**
1. 點擊 `[編輯資產]` -> 彈出 **Modal (Edit Asset)**。
2. 點擊 `[指派使用者]` -> 彈出 **Modal (Assign User)** 選擇使用者清單。
3. 點擊 `[報廢資產]` -> 彈出 **Modal (Confirm Dispose)** 二次確認。

---

## View 4: Review Screen (申請審查 - 分割窗格)

**[UI 佈局與元件]**
- **Split Pane Layout:**
  - **Left (List):** 待審查申請單垂直列表。
  - **Right (Detail):**
    - 申請詳細資訊：名稱、數量、總金額、申請人頭像與職稱。
    - **Progress Tracker:** 橫向進度條 (提交 -> 管理員審查 -> 財務審查 -> 核准)。
    - **Comment Box:** 顯示申請人的備註說明。
    - **Footer Actions:** `[核准通過]`, `[拒絕申請]`, `[退回修改]`。

**[使用者互動 Flow]**
1. 點擊左側列表項目 -> 更新右側詳情內容。
2. 點擊 `[核准通過]` -> 彈出確認 Modal -> 更新資產狀態為「維修中」或「採購中」，並觸發 Toast。
3. 點擊 `[拒絕申請]` -> 彈出 Modal 要求填寫「拒絕原因」。

---

## View 5: Holder Home (持有者首頁)

**[UI 佈局與元件]**
- **KPI Summary:** 我的設備數、維修中件數。
- **My Equipment Table:** 列出自己名下的設備與狀態。
- **Repair History:** 簡易列表顯示過去的維修單進度。
- **Floating/Bottom Action:** `[+ 提交維修申請]` 顯眼按鈕。

**[使用者互動 Flow]**
1. 點擊設備旁的 `[申請維修]` -> 彈出 **Modal (Repair Request)**。
2. 在 Modal 中輸入故障說明與「模擬上傳」照片 (Dropzone)。
3. 點擊 `[提交申請]` -> 導航至「我的維修申請」頁面追蹤進度。
