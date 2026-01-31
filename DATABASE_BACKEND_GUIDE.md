# Database Backend Configuration Guide

This project now supports both SQLite (for local development) and PostgreSQL (for production) through a database abstraction layer using SQLAlchemy.

## Overview

The system uses a database adapter pattern with two implementations:
- **SQLite**: Default, file-based database (no setup required)
- **PostgreSQL**: Production-ready relational database (requires PostgreSQL server)

## Quick Start

### Option 1: SQLite (Default - No Changes Needed)

The application continues to work with SQLite out of the box using the existing configuration:

```yaml
# config/sites.yaml
paths:
  db: data/index.db
```

### Option 2: PostgreSQL via Configuration File

Add a `database` section to your `config/sites.yaml`:

```yaml
# config/sites.yaml
database:
  type: postgresql
  host: localhost
  port: 5432
  database: ai_actuarial
  username: postgres
  password: your_password
```

### Option 3: PostgreSQL via Environment Variables

Set environment variables (useful for containerized deployments):

```bash
export DB_TYPE=postgresql
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=ai_actuarial
export DB_USER=postgres
export DB_PASSWORD=your_password
```

## Installation

### SQLite (Default)

No additional installation needed. SQLite support is built into Python.

### PostgreSQL

1. Install PostgreSQL server:
   ```bash
   # Ubuntu/Debian
   sudo apt-get install postgresql postgresql-contrib
   
   # macOS
   brew install postgresql
   
   # Windows
   # Download installer from https://www.postgresql.org/download/windows/
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   
   This includes:
   - `sqlalchemy>=2.0.0` - ORM for database abstraction
   - `psycopg2-binary>=2.9.0` - PostgreSQL driver

3. Create the database:
   ```bash
   # Connect to PostgreSQL
   psql -U postgres
   
   # Create database
   CREATE DATABASE ai_actuarial;
   
   # Create user (optional)
   CREATE USER ai_user WITH PASSWORD 'your_password';
   GRANT ALL PRIVILEGES ON DATABASE ai_actuarial TO ai_user;
   ```

## Usage

The application automatically detects and uses the appropriate database backend based on configuration.

### Basic Usage (Unchanged)

```python
from ai_actuarial.storage import Storage

# Legacy SQLite mode (backward compatible)
storage = Storage("data/index.db")
```

### Advanced Usage (New Backend Abstraction)

```python
from ai_actuarial.storage_factory import create_storage_from_config

# Load configuration
import yaml
with open("config/sites.yaml") as f:
    config = yaml.safe_load(f)

# Create storage with appropriate backend
storage = create_storage_from_config(config)

# Use storage as normal
storage.insert_file(...)
storage.close()
```

### Using StorageV2 Directly

```python
from ai_actuarial.storage_v2 import StorageV2

# PostgreSQL configuration
db_config = {
    "type": "postgresql",
    "host": "localhost",
    "port": 5432,
    "database": "ai_actuarial",
    "username": "postgres",
    "password": "your_password"
}

storage = StorageV2(db_config=db_config)
# Use as normal...
storage.close()
```

## Migration from SQLite to PostgreSQL

### Option 1: Export and Import Data

1. Export data from SQLite:
   ```bash
   ai-actuarial --config config/sites.yaml export --format json --output export.json
   ```

2. Configure PostgreSQL in `config/sites.yaml`

3. Import data (you may need to write a custom import script)

### Option 2: Use SQLAlchemy Migration Tools

For more complex migrations, consider using Alembic:

```bash
pip install alembic
alembic init migrations
# Configure alembic.ini and create migration scripts
```

## Configuration Reference

### Database Configuration Schema

```yaml
database:
  # Database type: 'sqlite' or 'postgresql'
  type: sqlite | postgresql
  
  # SQLite-specific settings
  path: data/index.db  # Database file path
  
  # PostgreSQL-specific settings
  host: localhost      # Database server hostname
  port: 5432          # Database server port
  database: ai_actuarial  # Database name
  username: postgres   # Database user
  password: secret     # Database password (consider using env vars!)
```

### Environment Variables

```bash
# Database type
DB_TYPE=sqlite|postgresql

# SQLite
DB_PATH=data/index.db

# PostgreSQL
DB_HOST=localhost
DB_PORT=5432
DB_NAME=ai_actuarial
DB_USER=postgres
DB_PASSWORD=your_password
```

## Architecture

### Components

1. **Storage** (`ai_actuarial/storage.py`): Original SQLite-only implementation (unchanged)
2. **StorageV2** (`ai_actuarial/storage_v2.py`): New SQLAlchemy-based implementation
3. **DatabaseBackend** (`ai_actuarial/db_backend.py`): Abstract backend interface
   - `SQLiteBackend`: SQLite implementation
   - `PostgreSQLBackend`: PostgreSQL implementation
4. **Models** (`ai_actuarial/db_models.py`): SQLAlchemy ORM models
5. **Factory** (`ai_actuarial/storage_factory.py`): Factory function for creating storage instances

### Design Patterns

- **Adapter Pattern**: DatabaseBackend provides a common interface for different databases
- **Factory Pattern**: create_storage_from_config() creates appropriate storage instances
- **Repository Pattern**: Storage classes abstract database operations

## Performance Considerations

### SQLite
- **Pros**: Simple, no server required, good for development
- **Cons**: Limited concurrency, not suitable for high-traffic production

### PostgreSQL
- **Pros**: Better concurrency, scalability, advanced features
- **Cons**: Requires server setup and maintenance

## Security Best Practices

1. **Never commit database passwords** to version control
2. **Use environment variables** for sensitive configuration
3. **Use strong passwords** for PostgreSQL users
4. **Restrict database access** using PostgreSQL's pg_hba.conf
5. **Use SSL/TLS** for PostgreSQL connections in production:
   ```yaml
   database:
     type: postgresql
     # Add SSL mode
     sslmode: require
   ```

## Troubleshooting

### PostgreSQL Connection Issues

1. **Connection refused**:
   - Ensure PostgreSQL server is running: `sudo systemctl status postgresql`
   - Check PostgreSQL is listening on the correct port: `netstat -an | grep 5432`

2. **Authentication failed**:
   - Verify username and password
   - Check PostgreSQL's `pg_hba.conf` file for authentication settings

3. **Database does not exist**:
   - Create the database: `createdb ai_actuarial`

### SQLite Issues

1. **Database is locked**:
   - Close all connections properly
   - WAL mode is enabled by default to reduce locking

2. **File permissions**:
   - Ensure the data directory is writable
   - Check file ownership and permissions

## Examples

See the examples below for common use cases:

### Example 1: Local Development (SQLite)

```yaml
# config/sites.yaml
paths:
  db: data/index.db
```

No code changes needed!

### Example 2: Production (PostgreSQL)

```yaml
# config/sites.yaml
database:
  type: postgresql
  host: db.example.com
  port: 5432
  database: ai_actuarial_prod
  username: ${DB_USER}  # Use environment variable
  password: ${DB_PASSWORD}  # Use environment variable
```

### Example 3: Docker Compose

```yaml
# docker-compose.yml
version: '3.8'
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: ai_actuarial
      POSTGRES_USER: ai_user
      POSTGRES_PASSWORD: secret
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
  
  app:
    build: .
    environment:
      DB_TYPE: postgresql
      DB_HOST: postgres
      DB_PORT: 5432
      DB_NAME: ai_actuarial
      DB_USER: ai_user
      DB_PASSWORD: secret
    depends_on:
      - postgres

volumes:
  postgres_data:
```

## Further Reading

- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [psycopg2 Documentation](https://www.psycopg.org/docs/)
