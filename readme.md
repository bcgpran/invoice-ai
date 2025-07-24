# Invoice Processing AI Assistant

A sophisticated, conversational AI agent for querying and managing invoice data, powered by Streamlit and a serverless Azure backend.

This application provides a user-friendly chat interface to interact with a powerful AI assistant. Users can upload invoices, purchase orders, and contracts, and then ask complex questions in natural language. The AI agent can query a SQL database with advanced fuzzy matching, generate reports, and even send emails with user consent, streamlining complex business intelligence tasks.

---

## Key Features

- **Conversational AI Agent**: Interact with your data using plain English. Ask complex questions, and the agent will understand your intent and perform the necessary actions.

- **Automated Document Processing**: Upload a PDF invoice, and the system uses an AI vision model (`gpt-4-vision`) to automatically extract its contents into a structured format for database entry.

- **Advanced SQL Search with Fuzzy Matching**: The agent can query the database to find invoices, POs, or contracts. It features a powerful, custom-built `SIMILARITY` function that finds matches even with typos or partial information.

- **On-the-Fly File Generation**: Ask the agent to export query results to a `CSV` file or generate a formal `PDF Verification Report`. Files are created securely and delivered via a temporary download link.

- **Secure, Consent-Based Email Workflow**: The agent can compose and send emails, but only after you review and approve a draft in the chat window. API keys are securely handled on the backend and never exposed to the client.

- **Multi-Session Management**: The sidebar allows you to create, rename, and switch between multiple chat sessions, keeping your conversations organized and context-aware.

---

## Application in Action

![Screenshot of the Chat Interface](screenshot.png)
*Application answering user's query and providing relevant files,  it can be downloaded by the user, mailed to someone as well.*




---

## Technical Setup and Configuration

This section provides a detailed guide for provisioning the necessary cloud infrastructure and configuring the project for local development.

### Azure Infrastructure Setup

This project requires several Azure services. The following steps guide you through provisioning the necessary infrastructure via the [Azure Portal](https://portal.azure.com).

#### 1. Azure Resource Group

First, create a Resource Group to hold all the project's resources, ensuring easy management and cleanup.

1.  Navigate to the Azure Portal and select `Resource groups`.
2.  Click `Create`, choose your subscription, and provide a name.
3.  Choose a region and click `Review + create`.

#### 2. Azure Storage Account

The storage account is critical for triggering the data ingestion functions and storing generated files.

1.  In the Azure Portal, click `Create a resource` and search for `Storage Account`.
2.  Select your new Resource Group and provide a unique name.
3.  After creation, navigate to the Storage Account and go to the `Containers` section.
4.  Create a container named `invoices`. The application will create subdirectories inside it automatically.
5.  Go to the `Access keys` section and copy one of the **Connection strings**. You will need this for both the `BLOB_CONNECTION_STRING` and `AzureWebJobsStorage` settings.

#### 3. Azure OpenAI Service

This service provides the AI models for the agent and vision capabilities.

1.  Click `Create a resource` and search for `Azure OpenAI`.
2.  Select your Resource Group and give the service a name.
3.  Navigate to the created service and go to `Model deployments` under `Management`.
4.  You must deploy two models:
    -   **Agent Model**: An instruction-following model like `gpt-4`. Give it a deployment name (e.g., `invoice-agent`). This name is your `AZURE_OPENAI_AGENT_DEPLOYMENT_NAME`.
    -   **Vision Model**: A multimodal model like `gpt-4-vision-preview`. Give it a deployment name (e.g., `invoice-vision`). This name is your `AZURE_OPENAI_VISION_DEPLOYMENT_NAME`.
5.  From the `Keys and Endpoint` section, copy the **API Key** and **Endpoint URL**.

#### 4. Azure SQL Database

This service will store all structured data from invoices, POs, and contracts.

1.  Click `Create a resource` and search for `SQL Database`.
2.  You will first need to create a `SQL server`. Provide a server name, admin login, and a secure password.
3.  Configure the database name (e.g., `InvoiceDB`).
4.  After creation, navigate to the `SQL Server` resource (not the database).
5.  Go to `Networking` -> `Public access`. Click `Add your client IP address` to allow local testing, and check the box for `Allow Azure services and resources to access this server`.
6.  Construct your `SQL_CONNECTION_STRING`. It will follow this format: 
```
Driver={ODBC Driver 18 for SQL Server};Server=tcp:YOUR_SERVER_NAME.database.windows.net,1433;Database=YOUR_DATABASE_NAME;Uid=YOUR_ADMIN_LOGIN;Pwd={YOUR_PASSWORD};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;
```

#### 5. Azure Function App

This is the serverless compute that runs all the backend logic.

1.  Click `Create a resource` and search for `Function App`.
2.  Select your Resource Group and provide a globally unique name.
3.  Set the `Runtime stack` to `Python` (e.g., version 3.9).
4.  On the `Hosting` tab, select the Storage Account you created earlier.

### External Services Setup

#### Brevo (for Email)

This service is used for sending emails.
1.  Create an account at `Brevo.com`.
2.  Navigate to `SMTP & API`.
3.  Generate an `API key` and note it down. This is your `BREVO_API_KEY`.
4.  Note the email address you will send from. This is your `BREVO_SENDER_EMAIL`.

### Local Project Setup

This guide will get the project running on your local machine.

#### 1. Prerequisites & Installation

-   Ensure you have Python 3.9+, Git, and the [Azure Tools for VS Code](https://marketplace.visualstudio.com/items?itemName=ms-vscode.vscode-node-azure-pack) extension pack

- Make sure to install the [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli-windows?view=azure-cli-latest&pivots=msi) as well to be able to run it locally 
-   Clone the repository :

    `git clone <your-repo-url>`
    
    `cd <your-repo-directory>`
    
    `python -m venv .venv`
    
    `source .venv/bin/activate` (On Windows, use `.venv\Scripts\activate`)

#### 2. Backend Configuration (`local.settings.json`)

Create a file named `local.settings.json` in the project root. This file stores your secrets for local development and is excluded by `.gitignore`. Populate it with the credentials you gathered from Azure.
```
{
    "IsEncrypted": false,
    "Values": {
        "FUNCTIONS_WORKER_RUNTIME": "python",
        "AzureWebJobsFeatureFlags": "EnableWorkerIndexing",
        "AzureWebJobsStorage": "Paste Storage connection string here",
        "BLOB_CONNECTION_STRING": "Paste Storage connection string here",
        "SQL_CONNECTION_STRING": "Paste SQL connection string here",
        "AZURE_OPENAI_API_KEY": "Paste your AOAI Key here",
        "AZURE_OPENAI_ENDPOINT": "Paste your AOAI Endpoint URL here",
        "AZURE_OPENAI_AGENT_DEPLOYMENT_NAME": "invoice-agent",
        "AZURE_OPENAI_VISION_DEPLOYMENT_NAME": "invoice-vision",
        "BREVO_API_KEY": "Paste your Brevo API Key here",
        "BREVO_SENDER_EMAIL": "your-sender@email.com",
        "API_ENDPOINT": "http://localhost:7071/api/invoice_agent_chat",
        "API_CODE": "",
        "INCOMING_BLOBS_PATH_PATTERN": "invoices/incoming/",
        "FINAL_REPORTS_PATH_PATTERN": "invoices/reports/",
        "SQL_REPORTS_PATH_PATTERN": "invoices/sql-load/",
        "PO_DATA_PATH_PATTERN": "invoices/master/",
        "CONTRACTS_PATH_PATTERN": "invoices/contracts/"
    }
}
```

#### 3. Frontend Configuration (`.streamlit/secrets.toml`)

Create a file at `.streamlit/secrets.toml` to store secrets for the Streamlit app.

##### For local development
```
API_ENDPOINT = "http://localhost:7071/api/invoice_agent_chat"
API_CODE = ""
```

##### For deployed app
```
# API_ENDPOINT = "https://<your-function-app-name>.azurewebsites.net/api/invoice_agent_chat"
# API_CODE = "<your-function-key>"
```
#### 4. Database Initialization

The database tables are created automatically the first time a function attempts to connect to them, thanks to the initialization checks within `shared_code/database_service.py`. No manual schema creation is needed.

---

## Deep Dive into the Application Architecture

This section explains the internal mechanics of the application, from the high-level data flow to the specific logic of the AI agent and its tools.

### High-Level Flow

The application operates on two primary, independent workflows:

1.  **Data Ingestion (Asynchronous & Event-Driven)**:
    -   A user uploads a file via the Streamlit frontend to a specific subfolder in Azure Blob Storage (e.g., `invoices/incoming/`).
    -   The `Blob Create` event triggers a corresponding Azure Function.
    -   This function processes the file (using AI vision for PDFs) and writes the structured data into the Azure SQL Database.
    -   This process is entirely decoupled from the user's chat session.

2.  **Chat Interaction (Synchronous & Request-Driven)**:
    -   A user sends a message in the chat UI.
    -   The Streamlit frontend makes a synchronous HTTP POST request to the `invoice_agent_chat` API endpoint.
    -   The agent orchestrator interprets the request, potentially using tools to query the database or generate files.
    -   A final response is sent back to the frontend and displayed to the user.

### The Backend: Azure Functions

The entire backend is orchestrated by `function_app.py`, which acts as a central router, registering all the modular blueprints from the `blueprints/` directory.

#### Data Ingestion Blueprints (Blob Triggered)

These functions are the automated entry points for all new data.

-   `invoice_ingestion_bp.py`: Triggered by new files in `invoices/incoming/`. It converts invoice PDFs to images, calls the Azure OpenAI Vision model to extract structured JSON data, and saves this data as a "final report" JSON file in another blob location.
-   `sql_processor_bp.py`: Triggered by the creation of a new "final report" JSON file. It parses this clean, structured JSON and inserts the data into the `Invoices` and `InvoiceLineItems` tables in the SQL database.
-   `po_data_bp.py` & `contract_processing_bp.py`: Similar blob-triggered functions that handle the processing of uploaded Purchase Order (CSV) and Contract (PDF/DOCX) files.

#### Interactive Agent Blueprint (HTTP Triggered)

-   `agent_orchestrator_bp.py`: This is the core of the application's intelligence. It exposes the `/invoice_agent_chat` endpoint and performs the following steps on each request:
    1.  Receives the user's query and conversation history.
    2.  Constructs a detailed **system prompt**. This crucial prompt instructs the AI on its personality, capabilities, and the exact workflow and format for using its tools.
    3.  Enters a loop, sending the conversation to the OpenAI model and receiving back either a final text answer or a request to call one or more tools.
    4.  Executes the requested tools and appends the results to the conversation history.
    5.  Continues this loop until the AI generates a final answer for the user.

### The Agent's "Brain": The `shared_code` Directory

The agent's power comes from the well-defined tools it can use.

#### Tool Definitions (`agent_tool_definitions.py`)

This file acts as the "menu" of available actions for the AI.

-   **Schema-in-Prompt Strategy**: The `get_invoice_agent_tools_definition` function dynamically injects the *entire SQL database schema* (all tables and columns) directly into the description of the `execute_sql_query_tool`. This is a critical design choice that empowers the LLM to write its own accurate SQL queries without needing separate fine-tuning or complex schema-mapping logic.

#### Tool Implementations (`agent_tool_implementations.py`)

This file contains the Python code that actually executes the tools.

-   **`execute_sql_query_tool` & `_rewrite_sql_for_similarity`**: This is the most sophisticated tool. The AI can request a search using a simple, abstract function: `SIMILARITY(Column, 'search_term')`. The `_rewrite_sql_for_similarity` helper then translates this into a powerful, multi-layered SQL query using `LIKE`, `SOUNDEX`, and normalized string comparisons to find fuzzy matches.

-   **`export_sql_query_to_csv_tool` & `generate_verification_report_pdf_tool`**: These tools follow a secure and scalable pattern for file generation:
    1.  Generate the file (CSV or PDF) entirely in memory.
    2.  Upload the file bytes to a private Azure Blob Storage container (`sessiondumps/`).
    3.  Generate a short-lived, secure **SAS (Shared Access Signature) URL** for the blob.
    4.  Return a JSON object containing this SAS URL to the agent, which is then formatted into a Markdown link for the user.

-   **The Two-Step Email Workflow**: This ensures security and user control.
    1.  **`request_user_email_consent`**: This is a "signal" tool. It does *not* send an email. It signals to the frontend that user consent is required, passing along the drafted email details.
    2.  **`send_email_with_attachments_tool`**: This tool actually sends the email. It is only ever called *after* the user has given explicit consent in the frontend UI. The sensitive `BREVO_API_KEY` is securely injected into this tool call on the backend, never exposing it to the user or the AI's primary prompt.

### The Frontend: Streamlit

The frontend provides a polished and interactive user experience.

-   `app.py`: The main entry point. It handles page configuration, session initialization, and calls the primary `render` functions.
-   `sidebar.py`: Manages the left-hand panel, which contains three expandable sections for session management, a list of generated files, and the data upload center.
-   `chat_window.py`: This is the most complex UI component. It is responsible for rendering the chat history and managing the interactive consent flow. It operates as a **state machine**:
    1.  **Default State**: Displays the chat and waits for user input. On input, it calls the backend API.
    2.  **`awaiting_confirmation` State**: If the API response contains `action_required: "user_consent_email"`, the UI switches to this state. It displays the email draft with "Proceed" and "Cancel" buttons instead of a chat input box.
    3.  **`sending_email` State**: If the user clicks "Proceed," the state changes again. It displays a spinner and makes the final API call to execute the approved email flow, then returns to the default state.

---

## Deployment & Usage

This section covers how to deploy the backend to Azure and how to run the Streamlit frontend to interact with the application.

### Deployment

#### 1. Deploying the Backend to Azure

While you can run the backend locally for development, it must be deployed to Azure for the full application to be accessible.

1.  **Deploy the Function App**: The recommended method is to use the [Azure Tools extension for Visual Studio Code](https://marketplace.visualstudio.com/items?itemName=ms-vscode.vscode-azurefunctions).
    -   Open the command palette (`Ctrl+Shift+P`), search for `Azure Functions: Deploy to Function App...`.
    -   Follow the prompts to select your subscription, the Function App resource you created, and confirm the deployment.
2.  **Configure Application Settings**: After deployment, the settings from your local `local.settings.json` file must be copied to the cloud configuration.
    -   In the Azure Portal, navigate to your Function App.
    -   Go to `Settings` -> `Configuration`.
    -   Under `Application settings`, add a new application setting for each key-value pair in the `Values` section of your `local.settings.json` file (e.g., `SQL_CONNECTION_STRING`, `BREVO_API_KEY`, etc.). This is a critical step.
3.  **Get the Function URL and Key**:
    -   In the `Functions` blade of your Function App, click on the `invoice_agent_chat` function.
    -   Click `Get Function Url`. Copy the URL. This will be your `API_ENDPOINT` for the deployed frontend. The key is included in the URL as `code=...`.

#### 2. Configuring the Frontend for Deployment

Before running the Streamlit frontend in a deployed environment (e.g., Streamlit Community Cloud, Azure App Service), you must update its secrets.

-   Update your `.streamlit/secrets.toml` file or configure the environment variables in your hosting service to use the deployed Function App's URL and key.

    #### .streamlit/secrets.toml for deployed app
    ```
    API_ENDPOINT = "https://<your-function-app-name>azurewebsites.net/api/invoice_agent_chat"
    API_CODE = "<your-function-key-from-azure>"
    ```

### Usage

Once the backend is deployed and the frontend is running, you can use the application.

1.  **Start the Frontend**:
    -   To run locally against your deployed backend, first ensure your `secrets.toml` is pointing to the Azure URL.
    -   Run the following command in your terminal:

        `streamlit run app.py`

2.  **Upload Data**:
    -   Open the `Data Upload Center` in the sidebar.
    -   Upload sample invoices, purchase orders, or contracts to the corresponding uploader.
    -   A success message will appear once the files are uploaded to Azure Blob Storage, which will trigger the backend processing.

3.  **Interact with the Agent**:
    -   Create a new chat session using the `➕ New Chat` button.
    -   Start asking questions. Here are some examples:

        `"Find the invoice with ID INV-123"`

        `"Are there any invoices from 'Global Tech Inc' that are overdue?"`

        `"Show me all line items for purchase order PO-005"`

        `"Please run a verification report for invoice INV-456."`

        `"Generate a CSV report of all invoices due this month and email it to my manager at manager@example.com."`


---

## In-Depth Look at the Agent's Toolkit

The intelligence and capabilities of the Invoice Processing AI Assistant are not derived from the LLM alone, but from the powerful and well-defined set of tools it can use. This section provides a deep dive into the design and implementation of these tools, which bridge the gap between natural language requests and concrete backend actions.

The agent's tools are defined by their schema in `shared_code/agent_tool_definitions.py` (the "what") and brought to life by their corresponding Python logic in `shared_code/agent_tool_implementations.py` (the "how").

### 1. The SQL Query Engine: Precision Search with a Fuzzy Touch

The cornerstone of the agent's data retrieval capability is its ability to interact with the Azure SQL database. This is primarily handled by a single, powerful tool.

-   **Tool:** `execute_sql_query_tool`

#### The "Schema-in-Prompt" Strategy

A critical design choice is the dynamic injection of the entire database schema directly into the tool's description. The `get_invoice_agent_tools_definition` function gathers the table and column definitions for `Invoices`, `InvoiceLineItems`, `MasterPOData`, and `Contracts` and embeds them in the prompt sent to the LLM.

-   **Why it's powerful:** This strategy empowers the LLM to write its own, accurate SQL queries for a wide range of questions without requiring complex schema mapping logic or separate fine-tuning. The agent "knows" what data is available and how tables relate to each other simply by reading the tool's description.

#### The `SIMILARITY` Abstraction: Bringing Fuzzy Search to SQL

To overcome the rigidity of traditional SQL `LIKE` clauses, the agent is presented with a simple, abstract function it can use for fuzzy matching: `SIMILARITY(ColumnName, 'search_term')`.

The agent is instructed to use this function when a user's query is imprecise (e.g., "find invoices from 'global tech'"). The real magic happens on the backend in the `_rewrite_sql_for_similarity` helper function.

-   **How it works:** This function intercepts the SQL query written by the LLM and translates the abstract `SIMILARITY()` call into a powerful, multi-layered SQL `CASE` statement. This statement attempts several matching techniques in order of confidence:
    1.  **Exact Match (100 score):** A perfect, case-insensitive match.
    2.  **Contains Match (80-90 score):** Uses `LIKE '%term%'`. It gives a higher score if the term appears at the beginning of the string.
    3.  **Normalized Match (75 score):** Compares the strings after stripping all spaces, commas, and periods, catching formatting differences.
    4.  **Soundex Match (70 score):** Compares the phonetic representations of the strings, catching spelling errors that sound similar.
    5.  **Normalized Contains Match (65 score):** A final attempt using `LIKE` on the normalized strings.

This approach effectively grants vector-search-like capabilities to a standard relational database, providing a robust and cost-effective solution for fuzzy data retrieval.

### 2. Secure, On-the-Fly File Generation

When a user requests a data export, the application never writes files to the local disk of the server. Instead, it uses a secure and scalable pattern for generating and delivering files.

-   **Tools:** `export_sql_query_to_csv_tool`, `generate_verification_report_pdf_tool`

#### The Secure Delivery Workflow

Both file-generation tools follow the same four-step, in-memory process:

1.  **Execute & Serialize:** The tool first runs the necessary SQL query to fetch the data. It then serializes the results into the target format (CSV or PDF) directly in memory, creating a byte stream.
2.  **Upload to Blob Storage:** The in-memory byte stream is uploaded to a designated private container in Azure Blob Storage (e.g., `invoices/sessiondumps/`). The file is given a unique, timestamped name.
3.  **Generate SAS URL:** The system then generates a **Shared Access Signature (SAS) URL** for the newly uploaded blob. This URL grants temporary, read-only access to that specific file.
4.  **Return Link to User:** The agent's tool returns a JSON object containing the SAS URL and filename. The agent orchestrator formats this into a clean Markdown link, which is displayed to the user for download.

-   **Benefits:** This architecture is highly secure as no files are made public and the access links automatically expire. It is also highly scalable and stateless, making it perfect for a serverless Azure Functions environment.

### 3. The Two-Step Email Workflow: Security Through User Consent

Allowing an AI to send emails presents a significant security challenge. The application solves this with a robust, two-step workflow that ensures user control and protects sensitive credentials.

#### Step 1: The "Signal" - `request_user_email_consent`

When a user asks to send an email, the agent does **not** call a tool that immediately sends it. Instead, it calls `request_user_email_consent`.

-   **Purpose:** This tool acts as a "signal" to the frontend. It takes the drafted email details (recipients, subject, body, and any attachment URLs) and passes them back in a special `action_required` response. It performs no other action.

#### Step 2: The "Consent" - The Frontend State Machine

The Streamlit frontend is designed to listen for this signal. When it receives the `action_required: "user_consent_email"` response, it changes its state:

-   The standard chat input is hidden.
-   A special UI element is displayed, showing the user the exact email draft and two buttons: **"Proceed"** and **"Cancel"**.

This **human-in-the-loop** step is critical. The user has the final say, preventing the agent from sending emails without explicit, real-time approval.

#### Step 3: The "Action" - `send_email_with_attachments_tool`

Only if the user clicks "Proceed" does the frontend make a *second, separate API call*. This new request instructs the backend to execute the final email sending flow.

-   **Purpose:** This is the tool that actually communicates with the Brevo email service.
-   **Secure Credential Handling:** The sensitive `BREVO_API_KEY` is retrieved from the backend's application settings and injected into the `send_email_with_attachments_tool` call at this final stage. It is never part of the LLM's conversation history, never exposed to the client, and only used after explicit user consent has been granted for a specific email.

This decoupled, consent-driven workflow provides a secure, transparent, and user-friendly way to grant the AI powerful action-taking capabilities.

---

## Hurdles, Challenges & Learnings

The current architecture is the result of significant iteration and learning. This section outlines key pivots made during the development process, detailing the challenges faced and the rationale behind the final design choices.

### 1. Evolution of the Data Extraction Pipeline

-   **Initial Approach**: The first version of the application used the standalone `Azure Document Intelligence` service to parse uploaded invoices. The goal was to receive a structured JSON file, which would then be verified by a separate LLM call.

-   **The Challenge**: The JSON output from `Azure Document Intelligence` was often inconsistent and, at times, inaccurate. This created a complex and brittle downstream process: the initial JSON had to be parsed, transformed into a different JSON format, and then sent along with the original document pages to an LLM for verification. This multi-step process was inefficient and prone to cascading errors.

-   **Solution & Rationale**: The pipeline was radically simplified by leveraging the multimodal capabilities of a single, powerful vision-enabled model (`gpt-4-vision-preview`). The new workflow sends the invoice pages directly to the model along with the desired JSON schema. The model performs both the optical character recognition (OCR) and the structured data extraction in a single step.

-   **Key Learning**: For complex extraction tasks, a powerful, context-aware multimodal LLM can be significantly more effective and efficient than a chain of specialized, single-purpose AI services. Simplifying the pipeline reduced points of failure and improved the quality of the extracted data.

### 2. Pivoting from Azure AI Search to SQL for Data Retrieval

-   **Initial Approach**: The project was originally designed to use `Azure AI Search` as the primary data store and retrieval engine. This involved creating multiple search indexes (for invoices, contracts, PO data), configuring indexers, and developing a suite of tools for the agent to query these indexes.

-   **The Challenge**: This approach struggled with two main issues. First, performing even basic mathematical calculations (e.g., summing totals, comparing amounts) across multiple retrieved documents was unreliable. It required dedicated tools and complex prompt engineering, which often failed. Second, the agent frequently hit context limits and struggled to reason effectively when the required information was spread across multiple search results from different indexes.

-   **Solution & Rationale**: The decision was made to switch to a traditional `Azure SQL` database. This provided immediate benefits:
    1.  **Reliable Calculations**: Complex calculations could be offloaded to the database engine itself via standard SQL queries.
    2.  **Simplified Tools**: The need for numerous, specialized tools was eliminated. The agent now primarily uses one powerful `execute_sql_query_tool`.
    3.  **Vector Search Alternative**: To retain fuzzy search capabilities, a custom `SIMILARITY` tool was developed. This tool translates a simple agent request into a powerful, multi-layered SQL query, effectively replicating the benefits of vector search for this use case without the overhead of a separate search service.

-   **Key Learning**: While AI search services are powerful, a relational database is often superior for applications requiring high-precision calculations, data integrity, and complex joins. A hybrid approach, using SQL for structured data and custom functions for "good enough" fuzzy matching, can provide a more robust and cost-effective solution.

### 3. Navigating Corporate Network and Security Constraints

-   **The Challenge**: During development and testing, several issues arose from operating within a managed corporate network, primarily due to security agents like Zscaler and Data Loss Prevention (DLP) policies.
    -   **Uploads Blocked**: `Zscaler` would intermittently block file uploads to Azure Blob Storage. Similarly, `DLP` policies were inconsistent, sometimes allowing a document upload and later blocking the exact same file.
    -   **SSL Certificate Errors**: The corporate network's SSL inspection would reject the certificate from the Azure Function App's response, preventing the frontend from receiving data.
    -   **Database Connectivity**: The corporate Wi-Fi would block outbound connections from a local machine to the Azure SQL database port.

-   **Solution & Rationale**: These issues are external to the application's code but critical for its functionality in an enterprise environment. The required solution is to engage with the IT security team to:
    1.  Whitelist the application's endpoints in `Zscaler` and `DLP`.
    2.  Obtain and install the necessary corporate certificate bundle to trust the SSL traffic.
    3.  Authorize outbound connections to the Azure SQL port.
    A temporary workaround for local development is to use a different, non-corporate network, but this is not a viable long-term solution.

-   **Key Learning**: When building applications for enterprise use, network security policies are a critical project dependency that must be addressed early in the development lifecycle.

---

## Future Enhancements & Roadmap

The current application provides a strong foundation, but there are two clear areas for future development to enhance its capabilities and enterprise-readiness.

### 1. Transition to Microsoft Graph for Enterprise-Grade Email Integration

The current email feature, while functional, relies on a third-party service (`Brevo`) and a generic API key. A more robust and secure solution would integrate directly with the enterprise's own Microsoft 365 ecosystem.

-   **Proposed Architecture**:
    1.  **App Registration**: Create an App Registration in `Microsoft Entra ID` (formerly Azure Active Directory).
    2.  **API Permissions**: Grant the application delegated permissions to the `Microsoft Graph API` to send email (`Mail.Send`) on behalf of a user.
    3.  **OAuth 2.0 Consent Flow**: When a user clicks "Proceed" to send an email, instead of the agent sending it directly, the application will initiate an OAuth 2.0 authentication flow.
    4.  **User Login**: The user will be redirected to the standard Microsoft login page to securely sign in and consent to the application sending an email on their behalf.
    5.  **Send Email**: Using the token acquired after login, the backend will call the Microsoft Graph API to send the email from the user's own account.

-   **Benefit**: This approach is significantly more secure, eliminates the need to manage a separate API key for email, and provides a clear audit trail as emails are sent directly from the user's mailbox.

### 2. Automated Anomaly Detection Pipeline

The current agent is reactive, answering questions based on user queries. A proactive feature would be to automatically flag invoices with potential issues during the ingestion process.

-   **Proposed Architecture**:
    1.  **Create an "Ingestion Orchestrator"**: A second, specialized agent orchestrator would be created, designed specifically for running a predefined sequence of validation checks.
    2.  **Define Anomaly Checks**: This orchestrator's tools and prompt would be focused on a checklist of tasks: checking for duplicate invoice numbers, comparing line item totals against the PO, validating vendor details, checking for contract compliance, etc.
    3.  **Create Anomaly Tables**: New tables will be added to the SQL database (e.g., `InvoiceAnomalies`) to store the results.
    4.  **Update the Ingestion Pipeline**: After the initial data is extracted, the invoice would be passed to this new Ingestion Orchestrator. It would run its checks and output a structured JSON of any detected anomalies.
    5.  **Log Anomalies**: A new function would parse this anomaly JSON and populate the `InvoiceAnomalies` table.
    6.  **Enhance the Chat Agent**: Finally, the main chat agent's tool definition would be updated to include the schema for the new anomaly tables.

-   **Benefit**: This would empower users to ask high-level questions like, `"Show me all invoices with calculation errors from last month"` or `"Which invoices have a mismatch with their purchase order?"`, transforming the tool from a simple data retriever into a proactive auditing assistant.