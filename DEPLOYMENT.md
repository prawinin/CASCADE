# KineticSketch AI - Deployment Guide

This guide covers deployment options for KineticSketch AI across different platforms and environments.

## Table of Contents

1. [Local Development](#local-development)
2. [Docker Deployment](#docker-deployment)
3. [Cloud Platforms](#cloud-platforms)
   - [Heroku](#heroku)
   - [Railway](#railway)
   - [Azure App Service](#azure-app-service)
   - [AWS Elastic Beanstalk](#aws-elastic-beanstalk)
4. [Production Checklist](#production-checklist)
5. [Troubleshooting](#troubleshooting)

---

## Local Development

### Prerequisites

- Python 3.11+
- Virtual environment manager (venv or conda)
- Git
- Optional: PyMOL, Ollama for full functionality

### Setup

```bash
# Clone repository
git clone https://github.com/prawinin/KineticSketch.git
cd KineticSketch

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Create .env file from template
cp .env.example .env

# Run application
python kinetic_sketch.py

# Open browser
# http://localhost:5000
```

---

## Docker Deployment

### Build and Run Locally

```bash
# Build image
docker build -t kinetic-sketch:latest .

# Run container
docker run -p 5000:5000 \
  -e FLASK_ENV=production \
  -e OLLAMA_API_URL=http://host.docker.internal:11434 \
  kinetic-sketch:latest
```

### Using Docker Compose

```bash
# Start all services (app + PyMOL + Ollama)
docker-compose up -d

# View logs
docker-compose logs -f app

# Stop all services
docker-compose down

# Check status
docker-compose ps
```

### Environment Variables

All configuration is managed via environment variables. See `.env.example` for complete reference:

```env
FLASK_ENV=production
HOST=0.0.0.0
PORT=5000
PYMOL_ENABLED=1
OLLAMA_ENABLED=1
MOLECULE_SIZE_LIMIT=200
SMILES_LENGTH_LIMIT=2000
```

---

## Cloud Platforms

### Heroku

**Estimated Cost:** $7-50/month (Eco dyno + add-ons)

#### Setup

1. **Create Heroku account** and install CLI:
   ```bash
   curl https://cli.heroku.com/install.sh | sh
   heroku login
   ```

2. **Create app:**
   ```bash
   heroku create kinetic-sketch-app
   ```

3. **Add buildpacks:**
   ```bash
   heroku buildpacks:add --index 1 heroku/python
   ```

4. **Configure environment:**
   ```bash
   heroku config:set FLASK_ENV=production
   heroku config:set PYMOL_ENABLED=0  # Heroku doesn't support PyMOL well
   heroku config:set OLLAMA_ENABLED=0  # Use external Ollama service
   ```

5. **Deploy:**
   ```bash
   git push heroku main
   ```

6. **Monitor:**
   ```bash
   heroku logs --tail
   heroku open
   ```

#### Notes
- PyMOL integration requires headless X server setup (complex)
- Consider using external Ollama service (Hugging Face, Together AI)
- Free tier has 30-minute sleep after inactivity

---

### Railway

**Estimated Cost:** $5-20/month (usage-based)

#### Setup

1. **Connect GitHub repository** to Railway:
   - Go to [railway.app](https://railway.app)
   - Connect GitHub account
   - Select KineticSketch repository

2. **Create new project** and add service

3. **Configure environment:**
   ```
   FLASK_ENV=production
   PORT=8000
   PYMOL_ENABLED=0
   OLLAMA_ENABLED=0
   ```

4. **Railway auto-detects Python** and deploys automatically

5. **View logs:**
   ```bash
   railway logs
   ```

#### Notes
- Very simple GitHub-based deployment
- No PyMOL/Ollama on free tier
- Competitive pricing with good performance

---

### Azure App Service

**Estimated Cost:** $10-50/month (B1 instance + storage)

#### Setup

1. **Install Azure CLI:**
   ```bash
   curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
   az login
   ```

2. **Create resource group:**
   ```bash
   az group create --name kinetic-sketch --location eastus
   ```

3. **Create App Service Plan:**
   ```bash
   az appservice plan create \
     --name kinetic-sketch-plan \
     --resource-group kinetic-sketch \
     --sku B1 --is-linux
   ```

4. **Create Web App:**
   ```bash
   az webapp create \
     --resource-group kinetic-sketch \
     --plan kinetic-sketch-plan \
     --name kinetic-sketch-app \
     --runtime "python:3.11"
   ```

5. **Deploy:**
   ```bash
   az webapp deployment source config-zip \
     --resource-group kinetic-sketch \
     --name kinetic-sketch-app \
     --src app.zip
   ```

6. **Configure settings:**
   ```bash
   az webapp config appsettings set \
     --resource-group kinetic-sketch \
     --name kinetic-sketch-app \
     --settings FLASK_ENV=production PYMOL_ENABLED=0
   ```

#### Notes
- Integrates with Azure services (Key Vault, Monitor, DevOps)
- Supports Linux and Windows
- Scaling and load balancing available

---

### AWS Elastic Beanstalk

**Estimated Cost:** $5-40/month (t3.small instance)

#### Setup

1. **Install EB CLI:**
   ```bash
   pip install awsebcli
   ```

2. **Initialize project:**
   ```bash
   eb init -p python-3.11 kinetic-sketch
   ```

3. **Create environment:**
   ```bash
   eb create kinetic-sketch-env
   ```

4. **Configure:**
   ```bash
   eb setenv FLASK_ENV=production PYMOL_ENABLED=0
   ```

5. **Deploy:**
   ```bash
   eb deploy
   ```

6. **Monitor:**
   ```bash
   eb logs
   eb status
   ```

#### Notes
- Highly scalable and reliable
- Integration with CloudWatch for monitoring
- Support for RDS databases
- More complex than Railway/Heroku

---

## Production Checklist

Before deploying to production:

### Code & Security
- [ ] All secrets in `.env`, not in code
- [ ] Set `FLASK_ENV=production`
- [ ] Set `SECRET_KEY` to strong random value
- [ ] Enable HTML sanitization (default: on)
- [ ] CORS disabled unless needed
- [ ] Debug mode disabled

### Performance
- [ ] Test with realistic molecule sizes
- [ ] Monitor response times
- [ ] Set appropriate timeouts:
  - `PYMOL_LISTEN_TIMEOUT=5` (seconds)
  - `OLLAMA_TIMEOUT=15` (seconds)
- [ ] Enable caching:
  - `PDB_CACHE_TTL=3600` (1 hour)
- [ ] Use production database for results

### Monitoring & Logging
- [ ] Logging enabled (`LOG_LEVEL=INFO`)
- [ ] Log format set to JSON for parsing
- [ ] Error tracking configured (Sentry optional)
- [ ] Health check endpoint accessible
- [ ] Disk space monitored (molecular results)

### Infrastructure
- [ ] HTTPS/TLS certificate configured
- [ ] Firewall rules set correctly
- [ ] CDN configured for static assets (optional)
- [ ] Load balancer configured (if multi-instance)
- [ ] Backup strategy in place

### Testing
- [ ] Integration tests passed
- [ ] Edge cases tested (invalid SMILES, large molecules)
- [ ] Service degradation tested (PyMOL/Ollama offline)
- [ ] Cross-browser testing (Chrome, Firefox, Safari, Edge)
- [ ] Mobile responsiveness verified

---

## Troubleshooting

### Container won't start

```bash
# Check logs
docker logs kinetic-sketch-app

# Common issues:
# - Missing dependencies: rebuild with `docker build --no-cache`
# - Port conflict: use different port with `-p 5001:5000`
# - Permission issues: ensure `/tmp` is writable
```

### Application is slow

```bash
# Check molecule size
# If processing >200 atoms, increase MOLECULE_SIZE_LIMIT cautiously

# Monitor memory
docker stats kinetic-sketch-app

# Check PyMOL/Ollama connectivity
curl http://pymol:9123/ping  # PyMOL health
curl http://ollama:11434/api/tags  # Ollama health
```

### PyMOL not connecting

```bash
# Verify PyMOL service is running
docker ps | grep pymol

# Check network connectivity
docker network inspect kinetic-sketch

# View PyMOL logs
docker logs kinetic-sketch-pymol
```

### Ollama not found

```bash
# Pull model in Ollama container
docker exec kinetic-sketch-ollama ollama pull mistral

# Verify model is available
curl http://localhost:11434/api/tags
```

### Disk space issues

```bash
# Check PDB cache size
du -sh /tmp/kinetic_sketch_pdb_cache

# Clear old cache (older than 24 hours)
find /tmp/kinetic_sketch_pdb_cache -mtime +1 -delete

# Adjust cache TTL in config
# Set PDB_CACHE_TTL=1800 for 30 minutes instead of 1 hour
```

---

## Health Checks

KineticSketch provides a health check endpoint for load balancers:

```bash
curl http://localhost:5000/health

# Response:
# {
#   "status": "healthy",
#   "timestamp": "2024-01-15T10:30:45Z",
#   "services": {
#     "pymol": "available",
#     "ollama": "available",
#     "database": "available"
#   }
# }
```

---

## Support & Issues

For deployment issues:
1. Check logs: `docker-compose logs -f app`
2. Review this guide for platform-specific notes
3. Create GitHub issue with:
   - Platform (Docker/Heroku/Railway/Azure/AWS)
   - Environment settings (FLASK_ENV, service versions)
   - Error message and logs
   - Steps to reproduce

---

**Last Updated:** 2024-01-15  
**Version:** 1.0.0
