#!/bin/bash

# API Endpoint Testing Script for QSuite
echo "🚀 Testing QSuite API Endpoints..."
echo "=================================="

BASE_URL="http://127.0.0.1:8000"

# Test health endpoint
echo "1. Testing Health Check..."
curl -s -o /dev/null -w "Health Check: %{http_code}\n" "$BASE_URL/health/"

# Test API schema
echo "2. Testing API Schema..."
curl -s -o /dev/null -w "API Schema: %{http_code}\n" "$BASE_URL/api/schema/"

# Test API docs
echo "3. Testing API Documentation..."
curl -s -o /dev/null -w "API Docs: %{http_code}\n" "$BASE_URL/api/docs/"

# Test ReDoc
echo "4. Testing ReDoc..."
curl -s -o /dev/null -w "ReDoc: %{http_code}\n" "$BASE_URL/api/redoc/"

# Test main API endpoint
echo "5. Testing Main API Endpoint..."
curl -s -o /dev/null -w "Main API: %{http_code}\n" "$BASE_URL/api/v1/"

# Test auth endpoints
echo "6. Testing Auth Endpoints..."
curl -s -o /dev/null -w "Token Obtain: %{http_code}\n" "$BASE_URL/api/auth/login/"
curl -s -o /dev/null -w "Token Refresh: %{http_code}\n" "$BASE_URL/api/auth/refresh/"
curl -s -o /dev/null -w "API Auth: %{http_code}\n" "$BASE_URL/api/v1/auth/"

# Test admin (should redirect or show login)
echo "7. Testing Admin..."
curl -s -o /dev/null -w "Admin: %{http_code}\n" "$BASE_URL/admin/"

echo ""
echo "✅ Test completed!"
echo ""
echo "📖 Open these URLs in your browser:"
echo "   API Docs: $BASE_URL/api/docs/"
echo "   ReDoc:    $BASE_URL/api/redoc/"
echo "   Admin:    $BASE_URL/admin/"
echo "   Health:   $BASE_URL/health/"
