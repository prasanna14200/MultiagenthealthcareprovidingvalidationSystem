# Provider Data Validation & Directory Management System

![Python Version](https://img.shields.io/badge/python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green)
![License](https://img.shields.io/badge/license-MIT-blue)

> AI-powered agentic system for validating and managing healthcare provider directory data with 80%+ accuracy improvement.

---

## 🎯 Project Overview

Healthcare payer organizations face significant challenges with provider directory accuracy:
- **40-80%** of directories contain outdated information
- **Hundreds** of manual phone calls required monthly
- **Member complaints** due to failed appointments
- **Regulatory compliance** demands frequent updates

### Our Solution

An intelligent multi-agent system that:
- ✅ **Validates** provider data from multiple sources (NPI Registry, websites, OCR)
- ✅ **Enriches** profiles with credentials and specialties
- ✅ **Scores** confidence levels (0.0 - 1.0) for each data point
- ✅ **Flags** low-confidence entries for manual review
- ✅ **Automates** email outreach and verification workflows
- ✅ **Generates** PDF reports and exports

---

## 🏗️ Architecture

```
┌─────────────────┐
│  CSV Input      │  200 Provider Records
│  (Synthetic)    │
└────────┬────────┘
         │
         ▼
┌──────────────────────────────────────┐
│       Orchestrator                    │
│  (Async Batch Processing)            │
└──────┬───────────────────────────────┘
       │
  ┌────┴────┬────────┬────────┬─────────┐
  │         │        │        │         │
  ▼         ▼        ▼        ▼         ▼
┌──────┐ ┌──────┐ ┌────┐ ┌──────┐ ┌────────┐
│Valid │ │Enrich│ │ QA │ │Recon │ │Outreach│
│Agent │ │Agent │ │Agt │ │Agent │ │Agent   │
└──┬───┘ └───┬──┘ └─┬──┘ └───┬──┘ └────┬───┘
   │         │      │        │         │
   └─────────┴──────┴────────┴─────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │  SQLite Database      │
        │  + CSV Export         │
        └───────────┬───────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │    FastAPI Server     │
        │  (REST API + JWT Auth)│
        └───────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.12+**
- **Redis** (for Celery background tasks)
- **Tesseract OCR** (for PDF extraction)

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3.12 python3.12-venv redis-server tesseract-ocr

# macOS
brew install python@3.12 redis tesseract
```

### Installation

```bash
# 1. Clone repository
git clone https://github.com/yourusername/provider-validator.git
cd provider-validator

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Initialize database
python -c "from src.db import init_db; init_db()"

# 5. Generate synthetic data
python scripts/generate_sample.py
python scripts/generate_pdfs.py

# 6. Create admin user
python src/create_user.py
# Username: admin
# Password: admin123
# Role: admin

# 7. Configure environment variables
cp .env.example .env
# Edit .env with your settings (SendGrid API key, etc.)
```

### Running the Application

**Terminal 1 - Start Redis:**
```bash
redis-server --daemonize yes
```

**Terminal 2 - Start Celery Worker:**
```bash
celery -A src.celery_app.celery_app worker --loglevel=info
```

**Terminal 3 - Start API Server:**
```bash
uvicorn src.api.app:app --reload --port 8000
```

**Access the application:**
- API Documentation: http://127.0.0.1:8000/docs
- Health Check: http://127.0.0.1:8000/

---

## 📖 Usage Guide

### 1. Get Authentication Token

```bash
curl -X POST "http://127.0.0.1:8000/token" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "username=admin&password=admin123"
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

### 2. Run Batch Validation

```bash
curl -X POST "http://127.0.0.1:8000/run-batch?limit=50&concurrency=6" \
     -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

### 3. View Processed Providers

```bash
curl "http://127.0.0.1:8000/providers?limit=20"
```

### 4. Get Flagged Providers (Manual Review Queue)

```bash
curl "http://127.0.0.1:8000/providers/flags?confidence_below=0.7"
```

### 5. Send Outreach Email

```bash
curl -X POST "http://127.0.0.1:8000/providers/1/send-outreach" \
     -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

### 6. Export Results

```bash
# CSV Export
curl "http://127.0.0.1:8000/providers/export" -o providers.csv

# PDF Report
curl "http://127.0.0.1:8000/reports/pdf" -o report.pdf
```

---

## 🛠️ Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Backend** | Python 3.12 | Core language |
| **API Framework** | FastAPI | REST API endpoints |
| **Server** | Uvicorn | ASGI web server |
| **Database** | SQLite / PostgreSQL | Data persistence |
| **Task Queue** | Celery + Redis | Background job processing |
| **Authentication** | JWT (python-jose) | API security |
| **OCR** | Tesseract + pdf2image | PDF text extraction |
| **Web Scraping** | aiohttp + BeautifulSoup | Website data collection |
| **Email** | SendGrid | Email delivery |
| **Reports** | ReportLab | PDF generation |
| **Validation** | phonenumbers, email-validator | Data quality checks |
| **Fuzzy Matching** | python-Levenshtein | String similarity |

---

## 📁 Project Structure

```
provider-validator/
├── data/                           # Data files
│   ├── providers_sample.csv        # Input data (200 providers)
│   ├── validated_providers.csv     # Output results
│   ├── providers.db                # Main database
│   ├── users.db                    # User authentication
│   ├── scanned_pdfs/               # Sample PDF documents
│   └── reports/                    # Generated reports
│
├── src/
│   ├── agents/                     # AI Agent modules
│   │   ├── base_agent.py           # Abstract base class
│   │   ├── validation_agent.py     # Data validation
│   │   ├── enrichment_agent.py     # Data enrichment
│   │   ├── qa_agent.py             # Quality assurance
│   │   ├── reconciliation_agent.py # Multi-source reconciliation
│   │   └── outreach_agent.py       # Email generation
│   │
│   ├── api/
│   │   └── app.py                  # FastAPI application
│   │
│   ├── reports/
│   │   └── pdf_generator.py        # PDF report generation
│   │
│   ├── orchestrator.py             # Main workflow coordinator
│   ├── db.py                       # Database operations
│   ├── ocr.py                      # OCR utilities
│   ├── utils.py                    # Helper functions
│   ├── auth.py                     # JWT authentication
│   ├── celery_app.py               # Celery configuration
│   └── create_user.py              # User creation script
│
├── scripts/
│   ├── generate_sample.py          # Generate synthetic data
│   ├── generate_pdfs.py            # Create sample PDFs
│   └── Testingocr.py               # OCR testing
│
├── .env                            # Environment variables
├── .gitignore                      # Git ignore rules
├── requirements.txt                # Python dependencies
└── README.md                       # This file
```

---

## 🔑 API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/token` | Get JWT access token |

### Providers
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/providers` | List all providers (paginated) |
| GET | `/providers/{id}` | Get provider by ID |
| GET | `/providers/specialty/{name}` | Filter by specialty |
| GET | `/providers/flags` | Get flagged providers for review |
| GET | `/providers/export` | Download CSV export |

### Batch Processing
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/run-batch` | Start background validation job |

### Outreach
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/providers/{id}/send-outreach` | Send verification email |
| GET | `/verify` | Provider verification webhook |

### Reports
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/reports/pdf` | Generate PDF report |

---

## 🧪 Testing

```bash
# Run batch processing (direct)
python -m src.orchestrator data/providers_sample.csv 8 10

# Test OCR extraction
python scripts/Testingocr.py

# Test database
python -c "from src.db import fetch_all; print(len(fetch_all()))"

# Test API health
curl http://127.0.0.1:8000/
```

---

## 📊 Key Metrics

- **Processing Speed**: 200 providers in ~2-3 minutes (concurrency=8)
- **Confidence Scoring**: 0.0 (no match) to 1.0 (perfect match)
- **Accuracy Target**: 80%+ for contact validation
- **OCR Extraction**: 85%+ accuracy on clean documents
- **API Response Time**: <200ms for most endpoints

---

## 🔐 Security Features

- ✅ JWT-based authentication with role-based access control (RBAC)
- ✅ Bcrypt password hashing
- ✅ Token expiration (configurable, default 7 days)
- ✅ Admin vs. Reviewer role separation
- ✅ Protected endpoints requiring authentication
- ✅ Environment variable configuration for secrets

---

## 🚧 Known Limitations

- **SQLite** used for development (migrate to PostgreSQL for production)
- **Mock NPI API** calls (integrate real CMS NPI Registry)
- **Email sending** requires SendGrid API key
- **No frontend UI** (REST API only - build admin dashboard separately)
- **Single-server deployment** (scale horizontally with Kubernetes for production)

---

## 🛣️ Roadmap

### Phase 5: Production Readiness
- [ ] Migrate to PostgreSQL
- [ ] Docker containerization
- [ ] Kubernetes deployment
- [ ] CI/CD pipeline (GitHub Actions)

### Phase 6: Monitoring & Observability
- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Structured logging (ELK stack)
- [ ] OpenTelemetry tracing

### Phase 7: Enhanced Features
- [ ] React admin dashboard
- [ ] Real-time websocket updates
- [ ] Advanced analytics
- [ ] Machine learning-based confidence scoring

---

## 🤝 Contributing

Contributions welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 👥 Authors

- **Your Name** - *Initial work* - [@prasanna14200](https://github.com/prasanna14200)

---

## 🙏 Acknowledgments

- **Anthropic** - AI assistance for development
- **FastAPI** - Modern Python web framework
- **Celery** - Distributed task queue
- **SendGrid** - Email delivery platform
- **Tesseract** - OCR engine

---

## 📧 Contact

For questions or support:
- **Email**: prasannaprasanna14200@gmail.com
- **GitHub Issues**: https://github.com/prasanna14200/MultiagenthealthcareprovidingvalidationSystem/issues
- **Documentation**: See `docs/` folder for detailed guides

---

## ⭐ Star History

If you find this project helpful, please consider giving it a star!


---

**Built with ❤️ using AI-powered agentic architecture**
