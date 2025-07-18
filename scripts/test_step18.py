#!/usr/bin/env python
"""
Test Runner for Step 18: Market Data Integration

Run this script to test all Step 18 features:
- Enhanced market data integration
- Technical indicator-based algorithm triggers  
- WebSocket market data enhancements
- Celery task synchronization
- API endpoint integration

Usage:
    python scripts/test_step18.py [--verbose] [--specific TEST_NAME]
"""

import os
import sys
import subprocess
import django
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.testing')
django.setup()

def run_tests(verbose=False, specific_test=None):
    """Run Step 18 integration tests"""
    
    # Define test modules for Step 18
    step18_tests = [
        'apps.order_management.tests.test_market_data_integration',
        'apps.order_management.tests.test_tasks',
        # Also run existing algorithm tests to ensure no regressions
        'apps.order_management.tests.test_algorithm_services.AlgorithmExecutionEngineTestCase.test_websocket_broadcasting',
        'apps.order_management.tests.test_algorithm_services.AlgorithmExecutionEngineTestCase.test_enhanced_market_data_integration',
    ]
    
    print("🧪 Running Step 18: Market Data Integration Tests")
    print("=" * 60)
    
    if specific_test:
        test_targets = [specific_test]
        print(f"🎯 Running specific test: {specific_test}")
    else:
        test_targets = step18_tests
        print(f"📋 Running {len(test_targets)} test modules")
    
    # Build Django test command
    cmd = ['python', 'manage.py', 'test']
    cmd.extend(test_targets)
    
    if verbose:
        cmd.append('--verbosity=2')
    else:
        cmd.append('--verbosity=1')
    
    # Add test-specific settings
    cmd.extend([
        '--settings=config.settings.testing',
        '--parallel=1',  # Avoid parallel conflicts with WebSocket tests
        '--keepdb'       # Speed up subsequent test runs
    ])
    
    print(f"🚀 Command: {' '.join(cmd)}")
    print()
    
    try:
        # Run the tests
        result = subprocess.run(cmd, cwd=PROJECT_ROOT, check=False)
        
        if result.returncode == 0:
            print("\n✅ All Step 18 tests passed!")
            print_success_summary()
        else:
            print(f"\n❌ Tests failed with exit code {result.returncode}")
            print_failure_help()
        
        return result.returncode
        
    except KeyboardInterrupt:
        print("\n⏹️  Tests interrupted by user")
        return 1
    except Exception as e:
        print(f"\n💥 Error running tests: {e}")
        return 1

def print_success_summary():
    """Print success summary with what was tested"""
    print("\n🎉 Step 18 Integration Verification Complete!")
    print("✅ Enhanced market data integration with yfinance")
    print("✅ Technical indicator-based algorithm triggers")
    print("✅ WebSocket market data consumer enhancements")
    print("✅ Celery task synchronization")
    print("✅ Algorithm market data API endpoint")
    print("✅ Error handling and edge cases")
    print("\n📊 Your algorithmic trading system now has:")
    print("   • Real-time market data feeds")
    print("   • Technical analysis intelligence")
    print("   • Live WebSocket streaming")
    print("   • Background synchronization")
    print("   • Professional API endpoints")

def print_failure_help():
    """Print help for test failures"""
    print("\n🔍 Test Failure Troubleshooting:")
    print("1. Check database setup: python manage.py migrate")
    print("2. Install requirements: pip install -r requirements/testing.txt")
    print("3. Check Redis connection for WebSocket tests")
    print("4. Verify all Step 18 changes were implemented correctly")
    print("5. Run with --verbose for detailed error output")
    print("\n📚 Common Issues:")
    print("   • Missing imports in new files")
    print("   • Database model conflicts")
    print("   • Redis/Channels configuration")
    print("   • WebSocket authentication setup")

def run_integration_check():
    """Quick integration verification"""
    print("\n🔧 Running Integration Verification...")
    
    try:
        # Test imports
        from apps.order_management.algorithm_services import AlgorithmExecutionEngine
        from apps.order_management.tasks import sync_algorithm_market_data
        from apps.trading_simulation.consumers import MarketDataConsumer
        print("✅ All imports successful")
        
        # Test enhanced market data method exists
        engine = AlgorithmExecutionEngine()
        if hasattr(engine, '_get_enhanced_market_data'):
            print("✅ Enhanced market data integration implemented")
        else:
            print("❌ Enhanced market data method missing")
            return False
        
        # Test technical indicator execution method exists  
        from apps.order_management.algorithm_services import SniperAlgorithm
        if hasattr(SniperAlgorithm, 'should_execute_with_indicators'):
            print("✅ Technical indicator execution implemented")
        else:
            print("❌ Technical indicator execution method missing")
            return False
        
        # Test API endpoint registration
        from django.urls import reverse
        try:
            # For ViewSet actions, the URL name is {basename}-{action_name}
            url = reverse('algorithmic-orders-market-data', kwargs={'pk': '12345678-1234-5678-9012-123456789012'})
            print("✅ API endpoint properly registered")
        except Exception:
            print("❌ API endpoint not registered correctly")
            return False
        
        print("✅ Integration verification passed!")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Integration error: {e}")
        return False

def main():
    """Main test runner"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Step 18 Test Runner')
    parser.add_argument('--verbose', '-v', action='store_true', 
                       help='Verbose test output')
    parser.add_argument('--specific', '-s', type=str,
                       help='Run specific test (e.g., test_enhanced_market_data_integration)')
    parser.add_argument('--integration-only', '-i', action='store_true',
                       help='Run only integration verification')
    
    args = parser.parse_args()
    
    if args.integration_only:
        success = run_integration_check()
        return 0 if success else 1
    
    # Run integration check first
    if not run_integration_check():
        print("\n❌ Integration verification failed. Fix issues before running tests.")
        return 1
    
    # Run tests
    return run_tests(verbose=args.verbose, specific_test=args.specific)

if __name__ == '__main__':
    sys.exit(main())
