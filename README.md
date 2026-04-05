# X-bookmark-downloader

A Python application that automatically downloads media from your X (Twitter) bookmarks, organizing files by creator with intelligent handling of quoted posts and robust error management.

## Features

✅ **Fetch Bookmarks** - Automatically retrieve bookmarks from X API v2  
✅ **Download Media** - Download images with resume support and videos using yt-dlp  
✅ **Quoted Posts** - Follow quoted posts (one level) with symlink references to original authors  
✅ **Deduplication** - Track processed items in SQLite database to prevent reprocessing  
✅ **Error Recovery** - Quarantine failed items for manual review and retry  
✅ **Flexible Tracking** - Choose between bookmark removal, local logging, or hybrid tracking  
✅ **Scheduled Execution** - Run via macOS launchd scheduler (or manual CLI)  
✅ **Multi-source Config** - Support for YAML files, .env files, and environment variables  

## Project Status

**Phase 1: Foundation ✅ COMPLETED**
- Project structure and Python package setup
- Multi-source configuration system with validation
- CLI entry point with 5 commands
- Logging infrastructure with rotating file handlers
- Comprehensive test suite (60+ tests)
- GitHub Actions CI/CD pipeline

**Phase 2-16: In Development**
- See [PLAN.md](PLAN.md) for full implementation roadmap

## Quick Start

### Prerequisites

- Python 3.9 or higher
- X API v2 bearer token (elevated access required)
- macOS (for launchd scheduling; Linux/Windows can use standard cron/Task Scheduler)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/andrewdavis92/x-bookmark-downloader.git
cd x-bookmark-downloader
```

2. Create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

### Configuration

1. Copy and configure the example files:
```bash
cp config.example.yaml config.yaml
cp .env.example .env
```

2. Add your X API bearer token to `.env`:
```bash
TWITTER_BEARER_TOKEN=your_token_here
```

3. Edit `config.yaml` with your preferences:
```yaml
twitter:
  bearer_token: ${TWITTER_BEARER_TOKEN}  # Read from .env
  request_timeout: 30

paths:
  downloads_directory: ~/Documents/X-Bookmarks
  logs_directory: ~/Library/Logs/bookmark-downloader

download:
  image_quality: high
  video_quality: best
  max_workers: 4
  timeout_seconds: 600
  retry_attempts: 3

processing:
  follow_quotes: true
  max_quote_depth: 1
  batch_size: 100

state_management:
  tracking_method: local_logging  # Options: local_logging, bookmark_removal, hybrid
  retention_days: -1  # -1 for unlimited

logging:
  level: INFO
  filename: bookmark_downloader.log
  max_bytes: 10485760
  backup_count: 5

quarantine:
  folder: quarantine
```

### Configuration Priority

Configuration is loaded in the following priority order (highest to lowest):
1. **Environment variables** with `BOOKMARK_DOWNLOADER_` prefix (e.g., `BOOKMARK_DOWNLOADER_DOWNLOAD_MAX_WORKERS=8`)
2. **Direct environment variables** (e.g., `TWITTER_BEARER_TOKEN=token`)
3. **YAML configuration file** (config.yaml or config.yml)
4. **.env file** (python-dotenv)
5. **Hardcoded defaults** (built into the application)

### Usage

```bash
# Download bookmarks (main functionality)
python -m bookmark_downloader download

# Verify setup and configuration
python -m bookmark_downloader verify_setup

# Show download statistics
python -m bookmark_downloader show_stats

# Retry failed downloads from quarantine
python -m bookmark_downloader retry_quarantine

# Clear local cache
python -m bookmark_downloader clear_cache

# Show help
python -m bookmark_downloader --help
```

## File Organization

Downloaded media is organized by creator username:

```
~/Documents/X-Bookmarks/
├── @username1/
│   ├── 1234567890_1.jpg        # First media from post
│   ├── 1234567890_2.mp4        # Second media from post
│   ├── 1234567890.txt          # Post content/metadata
│   ├── 1234567891_1.jpg        # Another post's media
│   └── 1234567891.txt
│
└── @username2/
    ├── 9876543210_1.jpg
    └── 9876543210.txt
```

### Quoted Post Handling

When a post contains a quote of another post, the media is organized under the original author's directory with a symlink reference from the quoting post:

```
~/Documents/X-Bookmarks/
├── @original_author/
│   ├── 5555555555_1.jpg        # Quoted post's media
│   └── 5555555555.txt
│
└── @quoter/
    ├── 1111111111_1.jpg
    ├── 1111111111.txt
    └── 1111111111_quoted_0.link  # Symlink to quoted post
```

## Database Schema

State is tracked in SQLite (state.db) with the following schema:

```sql
CREATE TABLE bookmarks (
    id INTEGER PRIMARY KEY,
    tweet_id TEXT UNIQUE NOT NULL,
    author_username TEXT NOT NULL,
    download_status TEXT NOT NULL,  -- processing, completed, failed, quarantined
    attempted_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_status ON bookmarks(download_status);
CREATE INDEX idx_author ON bookmarks(author_username);
CREATE INDEX idx_tweet_id ON bookmarks(tweet_id);
```

## Testing

Run the test suite:

```bash
# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ -v --cov=src/bookmark_downloader --cov-report=html

# Run specific test file
pytest tests/test_config.py -v

# Run specific test
pytest tests/test_config.py::TestConfigDefaults::test_defaults_exist -v
```

The test suite includes:
- **test_config.py** (26 tests): Configuration loading, validation, and path resolution
- **test_main.py** (26 tests): CLI commands and argument parsing
- **test_logger.py** (8 tests): Logging infrastructure and rotating file handlers

## Logging

Logs are written to the configured logs directory with automatic rotation:
- **File rotation**: 10MB per file, keeping 5 backups
- **Log levels**: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **Console output**: Formatted with timestamps
- **File output**: Detailed logging with module names

## Development

### Project Structure

```
X-bookmark-downloader/
├── src/bookmark_downloader/          # Main package
│   ├── config.py                     # Configuration management
│   ├── main.py                       # CLI entry point
│   ├── api/                          # X API integration (Phase 2)
│   ├── download/                     # Media downloading (Phase 4)
│   ├── processing/                   # Post processing (Phase 5-6)
│   ├── storage/                      # File storage (Phase 3, 6)
│   └── utils/                        # Utilities
├── tests/                            # Test suite
├── schedule/                         # macOS launchd config (Phase 12)
└── PLAN.md                           # Complete implementation roadmap
```

### Running Tests Locally

```bash
# Install test dependencies
pip install pytest pytest-cov

# Run tests with coverage
PYTHONPATH=src pytest tests/ -v --cov=src/bookmark_downloader

# Generate HTML coverage report
PYTHONPATH=src pytest tests/ --cov=src/bookmark_downloader --cov-report=html
```

### Code Quality

The project uses:
- **flake8** for linting (non-blocking)
- **mypy** for type checking (non-blocking)
- **pytest** for testing (required)

Code quality checks run automatically on GitHub Actions for all pushes to `main`, `claude/**`, `feature/**`, and `bugfix/**` branches.

## Architecture

See [PLAN.md](PLAN.md) for detailed architecture documentation including:
- High-level system design
- Module specifications
- Implementation phases
- Database schema
- Error handling strategy
- Edge case documentation

## Configuration Changes from Plan

During Phase 1 implementation, the following changes were made to the initial plan:

1. **YAML-only configuration**: Removed JSON configuration support to simplify implementation
2. **Default retention**: Changed retention_days default from 90 to -1 (unlimited) for safer default behavior
3. **Environment variable loading**: Enhanced .env file loading to use standard locations
4. **Configuration validation**: Added comprehensive validation with clear error messages

## Next Phase: API Integration (Phase 2)

The next phase will implement:
- X API v2 client with OAuth 2.0 authentication
- Bookmark fetching with pagination
- Rate limit handling and exponential backoff
- API response parsing and media extraction

See [PLAN.md](PLAN.md#phase-2-api-integration--authentication) for details.

## Contributing

This is a personal project but contributions are welcome. Please:
1. Create a feature branch (`feature/description`)
2. Make your changes with clear commit messages
3. Add tests for new functionality
4. Ensure all tests pass and linting checks succeed

## License

[Add your chosen license here]

## Support

For issues, questions, or feature requests, please see [PLAN.md](PLAN.md) for the complete project roadmap and architecture.

---

**Last Updated**: Phase 1 Complete  
**Current Focus**: Phase 2 - API Integration & Authentication
