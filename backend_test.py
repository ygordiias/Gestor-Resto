#!/usr/bin/env python3
"""
Backend API Testing for Digital Codex Restaurant Management System
Tests all API endpoints for functionality and integration
"""

import requests
import sys
import json
from datetime import datetime
from typing import Dict, List, Any

class RestaurantAPITester:
    def __init__(self, base_url="https://sacredserve.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.admin_user = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.test_data = {}

    def log(self, message: str, level: str = "INFO"):
        """Log test messages"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")

    def run_test(self, name: str, method: str, endpoint: str, expected_status: int, 
                 data: Dict = None, headers: Dict = None) -> tuple:
        """Run a single API test"""
        url = f"{self.base_url}/api/{endpoint}"
        test_headers = {'Content-Type': 'application/json'}
        
        if self.token:
            test_headers['Authorization'] = f'Bearer {self.token}'
        
        if headers:
            test_headers.update(headers)

        self.tests_run += 1
        self.log(f"Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=test_headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=test_headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=test_headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=test_headers, timeout=30)

            success = response.status_code == expected_status
            
            if success:
                self.tests_passed += 1
                self.log(f"✅ {name} - Status: {response.status_code}", "PASS")
                try:
                    return True, response.json()
                except:
                    return True, {}
            else:
                self.log(f"❌ {name} - Expected {expected_status}, got {response.status_code}", "FAIL")
                self.log(f"   Response: {response.text[:200]}", "FAIL")
                self.failed_tests.append({
                    'test': name,
                    'expected': expected_status,
                    'actual': response.status_code,
                    'response': response.text[:200]
                })
                return False, {}

        except Exception as e:
            self.log(f"❌ {name} - Error: {str(e)}", "ERROR")
            self.failed_tests.append({
                'test': name,
                'error': str(e)
            })
            return False, {}

    def test_database_seed(self):
        """Test database seeding"""
        self.log("=== Testing Database Setup ===")
        success, response = self.run_test(
            "Database Seed",
            "POST",
            "setup/seed",
            200
        )
        return success

    def test_authentication(self):
        """Test authentication endpoints"""
        self.log("=== Testing Authentication ===")
        
        # Test login with admin credentials
        success, response = self.run_test(
            "Admin Login",
            "POST",
            "auth/login",
            200,
            data={"email": "admin@digitalcodex.com", "password": "admin123"}
        )
        
        if success and 'access_token' in response:
            self.token = response['access_token']
            self.admin_user = response['user']
            self.log(f"✅ Logged in as: {self.admin_user['name']}")
            
            # Test get current user
            self.run_test("Get Current User", "GET", "auth/me", 200)
            return True
        
        return False

    def test_users_management(self):
        """Test user management endpoints"""
        self.log("=== Testing User Management ===")
        
        # Get all users
        success, users = self.run_test("Get Users", "GET", "users", 200)
        if success:
            self.test_data['users'] = users
        
        # Test other user logins
        test_users = [
            {"email": "garcom@digitalcodex.com", "password": "garcom123", "role": "waiter"},
            {"email": "caixa@digitalcodex.com", "password": "caixa123", "role": "cashier"},
            {"email": "cozinha@digitalcodex.com", "password": "cozinha123", "role": "kitchen"},
            {"email": "bar@digitalcodex.com", "password": "bar123", "role": "bar"},
        ]
        
        for user in test_users:
            self.run_test(
                f"Login {user['role']}",
                "POST",
                "auth/login",
                200,
                data={"email": user["email"], "password": user["password"]}
            )

    def test_categories_and_products(self):
        """Test categories and products endpoints"""
        self.log("=== Testing Categories and Products ===")
        
        # Get categories
        success, categories = self.run_test("Get Categories", "GET", "categories", 200)
        if success:
            self.test_data['categories'] = categories
        
        # Get products
        success, products = self.run_test("Get Products", "GET", "products", 200)
        if success:
            self.test_data['products'] = products
            self.log(f"Found {len(products)} products")

    def test_tables_management(self):
        """Test tables management"""
        self.log("=== Testing Tables Management ===")
        
        # Get all tables
        success, tables = self.run_test("Get Tables", "GET", "tables", 200)
        if success:
            self.test_data['tables'] = tables
            self.log(f"Found {len(tables)} tables")

    def test_orders_workflow(self):
        """Test complete order workflow"""
        self.log("=== Testing Orders Workflow ===")
        
        if not self.test_data.get('tables') or not self.test_data.get('products'):
            self.log("❌ Missing test data for orders", "ERROR")
            return False
        
        # Get a table and some products
        table = self.test_data['tables'][0]
        food_products = [p for p in self.test_data['products'] if p['type'] == 'food'][:2]
        drink_products = [p for p in self.test_data['products'] if p['type'] == 'drink'][:1]
        
        if not food_products or not drink_products:
            self.log("❌ No products available for testing", "ERROR")
            return False
        
        # Create order items
        order_items = []
        for product in food_products + drink_products:
            order_items.append({
                "product_id": product['id'],
                "product_name": product['name'],
                "quantity": 2,
                "unit_price": product['price'],
                "type": product['type'],
                "notes": "Test order item"
            })
        
        # Create order
        order_data = {
            "table_id": table['id'],
            "table_number": table['number'],
            "items": order_items,
            "waiter_id": self.admin_user['id'],
            "waiter_name": self.admin_user['name']
        }
        
        success, order = self.run_test(
            "Create Order",
            "POST",
            "orders",
            200,
            data=order_data
        )
        
        if success:
            self.test_data['test_order'] = order
            order_id = order['id']
            
            # Get order by ID
            self.run_test(f"Get Order {order_id}", "GET", f"orders/{order_id}", 200)
            
            # Get open orders
            self.run_test("Get Open Orders", "GET", "orders/open", 200)
            
            # Update item status (kitchen workflow)
            if order.get('items'):
                first_item = order['items'][0]
                self.run_test(
                    "Update Item Status to Preparing",
                    "PUT",
                    f"orders/{order_id}/item/{first_item['id']}/status",
                    200,
                    data={"status": "preparing"}
                )
                
                self.run_test(
                    "Update Item Status to Ready",
                    "PUT",
                    f"orders/{order_id}/item/{first_item['id']}/status",
                    200,
                    data={"status": "ready"}
                )

    def test_cash_register(self):
        """Test cash register operations"""
        self.log("=== Testing Cash Register ===")
        
        # Open cash register
        success, register = self.run_test(
            "Open Cash Register",
            "POST",
            "cash-register/open",
            200,
            data={"opened_by": "Test User", "initial_amount": 100.0}
        )
        
        if success:
            self.test_data['register'] = register
            
            # Get current register
            self.run_test("Get Current Register", "GET", "cash-register/current", 200)
            
            # Test withdrawal
            self.run_test(
                "Cash Withdrawal",
                "POST",
                "cash-register/withdrawal",
                200,
                data={"amount": 20.0, "reason": "Test withdrawal"}
            )
            
            # Test deposit
            self.run_test(
                "Cash Deposit",
                "POST",
                "cash-register/deposit",
                200,
                data={"amount": 50.0, "reason": "Test deposit"}
            )

    def test_close_order_and_register(self):
        """Test closing order and cash register"""
        self.log("=== Testing Order and Register Closure ===")
        
        if not self.test_data.get('test_order'):
            self.log("❌ No test order available", "ERROR")
            return False
        
        order = self.test_data['test_order']
        
        # Close order with payment
        payment_data = {
            "payments": [
                {"method": "cash", "amount": order['total']}
            ]
        }
        
        success = self.run_test(
            "Close Order",
            "POST",
            f"orders/{order['id']}/close",
            200,
            data=payment_data
        )
        
        if success:
            # Close cash register
            self.run_test(
                "Close Cash Register",
                "POST",
                "cash-register/close",
                200,
                data={"closed_by": "Test User"}
            )

    def test_reports(self):
        """Test reports endpoints"""
        self.log("=== Testing Reports ===")
        
        # Sales report
        self.run_test("Daily Sales Report", "GET", "reports/sales?period=daily", 200)
        self.run_test("Weekly Sales Report", "GET", "reports/sales?period=weekly", 200)
        self.run_test("Monthly Sales Report", "GET", "reports/sales?period=monthly", 200)
        
        # Profit report
        self.run_test("Daily Profit Report", "GET", "reports/profit?period=daily", 200)

    def test_stock_management(self):
        """Test stock management"""
        self.log("=== Testing Stock Management ===")
        
        # Get stock
        self.run_test("Get Stock", "GET", "stock", 200)
        
        # Get stock alerts
        self.run_test("Get Stock Alerts", "GET", "stock/alerts", 200)

    def test_invoices(self):
        """Test invoice system (MOCK)"""
        self.log("=== Testing Invoice System (MOCK) ===")
        
        # Get invoices
        self.run_test("Get Invoices", "GET", "invoices", 200)

    def run_all_tests(self):
        """Run all tests in sequence"""
        self.log("🚀 Starting Digital Codex API Tests")
        self.log(f"Testing against: {self.base_url}")
        
        try:
            # Core setup tests
            if not self.test_database_seed():
                self.log("❌ Database seed failed - stopping tests", "ERROR")
                return False
            
            if not self.test_authentication():
                self.log("❌ Authentication failed - stopping tests", "ERROR")
                return False
            
            # Feature tests
            self.test_users_management()
            self.test_categories_and_products()
            self.test_tables_management()
            self.test_orders_workflow()
            self.test_cash_register()
            self.test_close_order_and_register()
            self.test_reports()
            self.test_stock_management()
            self.test_invoices()
            
            return True
            
        except Exception as e:
            self.log(f"❌ Test suite failed with error: {str(e)}", "ERROR")
            return False

    def print_summary(self):
        """Print test summary"""
        self.log("=" * 50)
        self.log("🏁 TEST SUMMARY")
        self.log(f"Total Tests: {self.tests_run}")
        self.log(f"Passed: {self.tests_passed}")
        self.log(f"Failed: {len(self.failed_tests)}")
        
        if self.failed_tests:
            self.log("\n❌ FAILED TESTS:")
            for failure in self.failed_tests:
                if 'error' in failure:
                    self.log(f"  - {failure['test']}: {failure['error']}")
                else:
                    self.log(f"  - {failure['test']}: Expected {failure['expected']}, got {failure['actual']}")
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        self.log(f"\n📊 Success Rate: {success_rate:.1f}%")
        
        return success_rate >= 80  # Consider 80%+ as successful

def main():
    """Main test execution"""
    tester = RestaurantAPITester()
    
    try:
        success = tester.run_all_tests()
        tester.print_summary()
        
        return 0 if success else 1
        
    except KeyboardInterrupt:
        tester.log("Tests interrupted by user", "INFO")
        return 1
    except Exception as e:
        tester.log(f"Test execution failed: {str(e)}", "ERROR")
        return 1

if __name__ == "__main__":
    sys.exit(main())