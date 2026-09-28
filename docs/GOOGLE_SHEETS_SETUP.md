# Google Sheets Integration & Service Account Setup Guide

The **Personal Job Intelligence Platform** maps each resume profile to its own dedicated Google Spreadsheet. Google Sheets acts as the **operational dashboard** for reviewing high-precision job matches, recruiter contacts, and tracking manual applications.

---

## Architecture Principles

1. **PostgreSQL is the System of Record**: All jobs, profiles, verification states, and recruiter relationships originate and persist in PostgreSQL.
2. **Google Sheets is the Operational UI**: Spreadsheets are downstream projections of the PostgreSQL database.
3. **One Spreadsheet per Resume**: Each resume profile maps to its own dedicated workbook.
4. **Persistent Identifiers**: The `spreadsheet_id` is stored directly in PostgreSQL (`resumes.spreadsheet_id` and `resume_profiles.spreadsheet_id`). Spreadsheet titles are never used as database identifiers.
5. **No Hard-coded Credentials**: Authentication is handled exclusively through Google Cloud Service Account credentials loaded via environment variables or secret managers.

---

## 5-Tab Sheet Structure

Every provisioned spreadsheet automatically initializes with 5 structured tabs:

| Tab Name | Purpose | Key Content |
| :--- | :--- | :--- |
| **`Dashboard`** | High-level summary metrics | Total jobs tracked, active verified jobs, applications submitted, system health. |
| **`Jobs`** | Actionable job listings | **Exact 27 columns** detailing matched skills, missing requirements, URLs, and recruiter links. |
| **`Recruiters`** | Discovered hiring team contacts | Recruiter name, verified LinkedIn profile, company, contact details, confidence score. |
| **`Applications`** | Manual application tracker | Application status (`To Apply`, `Applied`, `Interviewing`, `Offer`, `Rejected`), submission date, notes. |
| **`System Status`** | Audit trail & verification logs | Liveness probe results, HTTP status codes, last scan timestamp, scraper health. |

### The Exact 27 Columns in the `Jobs` Tab

```
1.  Date Found
2.  Job Title
3.  Company
4.  Experience
5.  Location
6.  Work Mode
7.  Job Link
8.  Direct Application Link
9.  Source
10. Job ID
11. First Seen
12. Last Verified
13. Verification Status
14. Source Quality
15. Match Level
16. Why It Matches
17. Required Skills
18. Skills You Have
19. Missing / Improve
20. Resume
21. Recruiter 1
22. Recruiter 2
23. Recruiter 3
24. Application Status
25. Applied Date
26. Follow-up Date
27. Notes
```

---

## Step-by-Step Setup Instructions

### Step 1: Create a Google Cloud Project
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Click the project dropdown in the top header and click **New Project**.
3. Name your project (e.g., `Job-Intelligence-Platform`) and click **Create**.

### Step 2: Enable Required Google APIs
1. In your project, navigate to **APIs & Services > Library**.
2. Search for **Google Sheets API** and click **Enable**.
3. Search for **Google Drive API** and click **Enable**.
   *(Google Drive API is required for creating and sharing spreadsheets).*

### Step 3: Create a Service Account
1. Navigate to **IAM & Admin > Service Accounts**.
2. Click **Create Service Account**.
3. Service Account details:
   - **Service account name**: `job-intelligence-sheets-sa`
   - **Service account ID**: `job-intelligence-sheets-sa` (auto-filled)
   - **Description**: `Service account for automated Google Sheets dashboard generation`
4. Click **Create and Continue**.
5. Role assignment: You can assign **Editor** (or leave unassigned since permissions are granted per-sheet).
6. Click **Done**.

### Step 4: Create and Download the JSON Key
1. In the Service Accounts list, click on your newly created service account (`job-intelligence-sheets-sa@...`).
2. Navigate to the **Keys** tab.
3. Click **Add Key > Create new key**.
4. Select **JSON** as the key type and click **Create**.
5. A JSON key file will download to your computer.

### Step 5: Configure Credentials in the Project
1. Rename the downloaded file to `service_account.json`.
2. Move the file into the project's `credentials/` folder:
   ```text
   Automate_Job_Finder/
   └── credentials/
       └── service_account.json
   ```
   *(Note: `credentials/` and `service_account*.json` are already protected in `.gitignore` and will never be committed to git).*

3. Update your `.env` file:
   ```env
   # Google Sheets Integration
   GOOGLE_SERVICE_ACCOUNT_FILE=credentials/service_account.json
   GOOGLE_SHEETS_SHARE_USER_EMAIL=your_personal_email@gmail.com
   ```
   *(Setting `GOOGLE_SHEETS_SHARE_USER_EMAIL` ensures that every newly created spreadsheet is immediately shared with your Google Drive with full Editor access).*

---

## Live Verification

To verify that your Google credentials are authenticated and can create, format, write, update, and read from Google Sheets:

```bash
# Activate your virtual environment
.venv\Scripts\Activate.ps1   # Windows
source .venv/bin/activate    # Linux/macOS

# Run the live verification CLI tool
python scripts/verify_sheets.py
```

The script will:
1. Authenticate with Google Sheets & Drive APIs.
2. Create a live test spreadsheet with all 5 required tabs.
3. Format headers (bold, frozen header row).
4. Share the sheet with your personal email.
5. Write a verified test record.
6. Update the record.
7. Read back the updated data.
8. Output the live clickable Google Sheets URL.
