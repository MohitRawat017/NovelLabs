#!/usr/bin/env python3
"""
NovelLabs API Testing Script
Tests all critical endpoints after deployment
"""

import requests
import json
import sys
from typing import Dict, Any

# API base URL
BASE_URL = "https://novellabs.onrender.com"

# Test results
results = []


def test_endpoint(name: str, url: str, method: str = "GET", 
                  data: Dict[Any, Any] = None, expected_status: int = 200) -> bool:
    """Test a single endpoint"""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"URL: {url}")
    print(f"Method: {method}")
    
    try:
        if method == "GET":
            response = requests.get(url, timeout=30)
        elif method == "POST":
            response = requests.post(url, json=data, timeout=30)
        else:
            print(f"❌ Unsupported method: {method}")
            return False
        
        print(f"Status: {response.status_code}")
        
        # Check status
        if response.status_code != expected_status:
            print(f"❌ FAILED: Expected {expected_status}, got {response.status_code}")
            print(f"Response: {response.text[:200]}")
            results.append({
                'test': name,
                'status': 'FAILED',
                'reason': f"Wrong status: {response.status_code}"
            })
            return False
        
        # Try to parse JSON
        try:
            data = response.json()
            print(f"✅ PASSED")
            print(f"Response preview: {json.dumps(data, indent=2)[:200]}...")
            results.append({
                'test': name,
                'status': 'PASSED',
                'data': data
            })
            return True
        except json.JSONDecodeError:
            print(f"❌ FAILED: Invalid JSON response")
            print(f"Response: {response.text[:200]}")
            results.append({
                'test': name,
                'status': 'FAILED',
                'reason': 'Invalid JSON'
            })
            return False
            
    except requests.Timeout:
        print(f"❌ FAILED: Request timeout (30s)")
        results.append({
            'test': name,
            'status': 'FAILED',
            'reason': 'Timeout'
        })
        return False
    except Exception as e:
        print(f"❌ FAILED: {str(e)}")
        results.append({
            'test': name,
            'status': 'FAILED',
            'reason': str(e)
        })
        return False


def run_tests():
    """Run all API tests"""
    print("="*60)
    print("NovelLabs API Test Suite")
    print("="*60)
    
    # Test 1: Root endpoint
    test_endpoint(
        "Root Health Check",
        f"{BASE_URL}/"
    )
    
    # Test 2: API health check
    test_endpoint(
        "API Health Check",
        f"{BASE_URL}/api/health"
    )
    
    # Test 3: List novels (CRITICAL - uses DB)
    test_endpoint(
        "List Novels (Database Query)",
        f"{BASE_URL}/api/novels"
    )
    
    # Test 4: List novels with pagination
    test_endpoint(
        "List Novels with Pagination",
        f"{BASE_URL}/api/novels?limit=10&offset=0"
    )
    
    # Test 5: Manual sync (POST)
    test_endpoint(
        "Manual Sync Novels",
        f"{BASE_URL}/api/novels/sync",
        method="POST"
    )
    
    # Test 6: Get single novel (if we have one)
    # Use actual novel slug from database
    test_endpoint(
        "Get Single Novel",
        f"{BASE_URL}/api/novels/lord-of-the-mysteries",
        expected_status=200
    )
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for r in results if r['status'] == 'PASSED')
    failed = sum(1 for r in results if r['status'] == 'FAILED')
    total = len(results)
    
    print(f"\nTotal Tests: {total}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"Success Rate: {(passed/total*100):.1f}%")
    
    print("\n" + "="*60)
    print("DETAILED RESULTS")
    print("="*60)
    
    for result in results:
        status_icon = "✅" if result['status'] == 'PASSED' else "❌"
        print(f"\n{status_icon} {result['test']}")
        if result['status'] == 'FAILED':
            print(f"   Reason: {result.get('reason', 'Unknown')}")
    
    # Return exit code
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)