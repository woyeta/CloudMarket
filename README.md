# CloudMarket

A Django-based cloud application marketplace with a server-rendered frontend and a RESTful API built with Django REST Framework.

The app supports two user roles: **Customers** and **Developers**, enabling developers to publish applications and customers to browse, purchase, review, and download them. The REST API is documented with an auto-generated OpenAPI schema served via Swagger UI and ReDoc.

## Installation

Clone the repository and install dependencies:

```bash
git clone https://github.com/woyeta/CloudMarket.git
cd CloudMarket
pip install -r requirements.txt
```

Create a `.env` file from the example and apply migrations:

```bash
cp .env.example .env
python manage.py migrate
```

## Running the App

Run the Django development server:

```bash
python manage.py runserver
```

### API Documentation

Once the server is running, interactive API docs are available at:

- **Swagger UI**: [`/api/schema/swagger-ui/`](http://localhost:8000/api/schema/swagger-ui/)
- **ReDoc**: [`/api/schema/redoc/`](http://localhost:8000/api/schema/redoc/)

### Running Tests

```bash
python manage.py test
```
