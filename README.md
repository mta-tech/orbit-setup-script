# Orbit Setup Script

A Python script for setting up Orbit services including KAI (Knowledge Agent for Intelligence) and geolocation features.

## Features

- Automated deployment of Orbit services using Docker Compose
- KAI service configuration with database connections
- Support for both connection URI and individual database parameters
- Docker network management for service communication

## Prerequisites

- Python 3.11 or higher
- Docker and Docker Compose
- PostgreSQL database
- UV package manager

## Installation

1. Clone this repository:
```bash
git clone [repository-url]
cd orbit-setup-script
```

2. Install dependencies using uv:
```bash
uv pip install -e .
```

4. Create environment files:

### `.env.kai`
```env
# Application Configuration
APP_NAME=KAI API
APP_DESCRIPTION="KAI stands for Knowledge Agent for Intelligence query. This project brings the Gen AI component to be able to embedded into the database so that it can perform analytics and document searches with natural language."
APP_VERSION=1.0.0
APP_ENVIRONMENT=LOCAL

# Server Configuration
APP_HOST=0.0.0.0
APP_PORT=8005
APP_ENABLE_HOT_RELOAD=0

# Typesense Configuration
TYPESENSE_API_KEY=kai_typesense
TYPESENSE_HOST=orbit_typesense
TYPESENSE_PORT=8108
TYPESENSE_PROTOCOL=HTTP
TYPESENSE_TIMEOUT=2

# Model Configuration
CHAT_FAMILY="openai"
CHAT_MODEL="gpt-4o-mini"

EMBEDDING_FAMILY="google"
EMBEDDING_MODEL="models/text-embedding-004"
EMBEDDING_DIMENSIONS=768

# API Keys
OPENAI_API_KEY="your-openai-api-key"
OPENROUTER_API_KEY="your-openrouter-api-key"
OPENROUTER_API_BASE="https://openrouter.ai/api/v1"
MODEL_GARDEN_API_KEY="your-model-garden-api-key"
MODEL_GARDEN_API_BASE="https://console.labahasa.ai/v1"
GOOGLE_API_KEY="your-google-api-key"

# Additional Settings
OLLAMA_API_BASE="http://localhost:11434"
HUGGINGFACEHUB_API_TOKEN=""
GLINER_API_BASE=""

# Agent Configuration
AGENT_MAX_ITERATIONS=10
DH_ENGINE_TIMEOUT=150
SQL_EXECUTION_TIMEOUT=60
UPPER_LIMIT_QUERY_RETURN_ROWS=50

# Security
ENCRYPT_KEY="your-encryption-key"
```

### `.env.orbit`
```env
ORBIT_SERVER_API_URL=http://10.184.0.2:9003/api/v1/edge
ORBIT_API_KEY=your-orbit-api-key
KAI_URL=http://orbit-text2sql-agent:8005/api
MODEL_FAMILY=google
MODEL_NAME=gemini-2.0-flash
WORKER_THREAD_COUNT=20
```

## Usage

The script can be run either with a config file or with command-line arguments:

### Using Config File

```bash
python setup.py --config config.json
```

The config.json file should have the following structure:
```json
{
  "api_key": "your-api-key",
  "process_type": "initial_provisioning_orbit",
  "process_id": "optional-process-id",
  "step_order": 0,
  "data": {
    "jwt_token": "your-jwt-token",
    "orbit_configuration": {
      "connection_string": "postgresql://user:password@host:port/database",
      "db_connection": {
        "host": "localhost",
        "port": 5432,
        "database": "your_database",
        "username": "your_username",
        "password": "your_password"
      }
    },
    "agent": {
      "agent_name": "your-agent-name",
      "agent_description": "your-agent-description"
    }
  }
}
```

### Using Command Line Arguments

Basic usage with database URI:
```bash
python setup.py \
  --api-key "your-api-key" \
  --db-connection-uri "postgresql://user:password@host:port/database"
```

With individual database parameters:
```bash
python setup.py \
  --api-key "your-api-key" \
  --db-host "localhost" \
  --db-port 5432 \
  --db-name "your_database" \
  --db-user "your_username" \
  --db-password "your_password"
```

## Available Arguments

### Configuration Source (Required, choose one)
- `--config`: Path to config.json file
- `--api-key`: API Key for authentication

### Database Connection (Required when not using config file)
- `--db-connection-uri`: Full database connection URI
  OR
- `--db-host`: Database host
- `--db-port`: Database port (default: 5432)
- `--db-name`: Database name
- `--db-user`: Database username
- `--db-password`: Database password

### Agent Configuration (Optional)
- `--agent-name`: Name of the agent
- `--agent-description`: Description of the agent
- `--jwt-token`: JWT token for authentication

## Process Types

The script supports different process types that determine the required parameters:

1. **initial_provisioning_orbit**: Full setup of Orbit services including KAI and worker deployment
   - Requires API key
   - Deploys all Docker services
   - Configures KAI service

2. **create_agent_orbit**: Creates an agent when services are already deployed
   - API key is optional (assumes KAI and worker services are already running)
   - Only configures database connection and schema

## Docker Services

The script sets up the following Docker services:

1. **orbit-typesense**: Typesense search engine
   - Port: 8108
   - Persistent volume for data storage

2. **orbit-text2sql-agent**: KAI service for text-to-SQL conversion
   - Port: 8005
   - Depends on orbit-typesense

3. **orbit-worker**: Orbit worker service
   - Depends on orbit-text2sql-agent

All services are connected through the `agentic_network` Docker network.

## Error Handling

The script includes comprehensive error handling for:
- Database connection issues
- Docker service deployment failures
- Configuration errors

If any errors occur, the script will provide detailed error messages and exit gracefully.

## Notes

- The script automatically creates the required Docker network if it doesn't exist
- Services are configured to restart on failure
- The KAI service requires some time to initialize (10 seconds delay after startup)
- All sensitive information should be properly secured in the environment files