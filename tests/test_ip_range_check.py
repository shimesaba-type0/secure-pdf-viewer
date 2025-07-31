#!/usr/bin/env python3
"""
IP範囲チェック機能のテスト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.pdf_security_settings import is_referrer_allowed, validate_allowed_domains


def test_ip_range_functionality():
    """IP範囲チェック機能の動作テスト"""
    print("=== IP範囲チェック機能テスト ===\n")
    
    # テストケース定義
    test_cases = [
        # [referer_url, allowed_domains, expected_result, description]
        
        # ドメイン名テスト
        ["http://localhost/app", ["localhost", "127.0.0.1"], True, "ローカルホスト - 完全一致"],
        ["https://app.example.com/page", ["example.com"], True, "サブドメイン許可"],
        ["https://app.example.com/page", [".example.com"], True, "明示的サブドメイン許可"],
        ["https://malicious.com/page", ["example.com"], False, "異なるドメイン"],
        
        # IPアドレステスト
        ["http://127.0.0.1/app", ["127.0.0.1"], True, "IP完全一致"],
        ["http://192.168.1.100/app", ["192.168.1.50"], False, "IP不一致"],
        
        # CIDR表記テスト
        ["http://10.0.0.50/app", ["10.0.0.0/24"], True, "CIDR範囲内"],
        ["http://10.0.1.50/app", ["10.0.0.0/24"], False, "CIDR範囲外"],
        ["http://192.168.1.100/app", ["192.168.0.0/16"], True, "大きなCIDR範囲内"],
        ["http://172.16.5.10/app", ["192.168.0.0/16"], False, "大きなCIDR範囲外"],
        
        # IP範囲（ハイフン）テスト
        ["http://192.168.1.50/app", ["192.168.1.1-192.168.1.100"], True, "IP範囲内"],
        ["http://192.168.1.150/app", ["192.168.1.1-192.168.1.100"], False, "IP範囲外"],
        ["http://192.168.1.1/app", ["192.168.1.1-192.168.1.100"], True, "IP範囲の境界値（開始）"],
        ["http://192.168.1.100/app", ["192.168.1.1-192.168.1.100"], True, "IP範囲の境界値（終了）"],
        
        # 複合テスト
        ["http://10.0.0.25/app", ["localhost", "10.0.0.0/24", "example.com"], True, "複数パターン - CIDR一致"],
        ["http://example.com/app", ["localhost", "10.0.0.0/24", "example.com"], True, "複数パターン - ドメイン一致"],
        ["http://malicious.com/app", ["localhost", "10.0.0.0/24", "example.com"], False, "複数パターン - 全て不一致"],
        
        # エラーケース
        ["", ["localhost"], False, "空のreferer"],
        ["http://localhost/app", [], False, "空の許可リスト"],
        ["invalid-url", ["localhost"], False, "不正なURL"],
    ]
    
    # テスト実行
    passed = 0
    failed = 0
    
    for i, (referer, allowed, expected, description) in enumerate(test_cases, 1):
        try:
            result = is_referrer_allowed(referer, allowed)
            
            if result == expected:
                print(f"✅ Test {i:2d}: {description}")
                passed += 1
            else:
                print(f"❌ Test {i:2d}: {description}")
                print(f"    Expected: {expected}, Got: {result}")
                print(f"    Referer: {referer}")
                print(f"    Allowed: {allowed}")
                failed += 1
                
        except Exception as e:
            print(f"💥 Test {i:2d}: {description} - Exception: {e}")
            failed += 1
    
    print(f"\n=== テスト結果 ===")
    print(f"成功: {passed}, 失敗: {failed}")
    
    if failed == 0:
        print("🎉 全てのテストに成功しました！")
    
    return failed == 0


def test_validation_functionality():
    """設定値検証機能のテスト"""
    print("\n=== 設定値検証機能テスト ===\n")
    
    test_cases = [
        # [domains, expected_valid, description]
        [["localhost", "127.0.0.1"], True, "正常なドメイン・IP"],
        [["10.0.0.0/24"], True, "正常なCIDR"],
        [["192.168.1.1-192.168.1.100"], True, "正常なIP範囲"],
        [["example.com", ".subdomain.com"], True, "ドメイン名各種"],
        [["10.0.0.0/33"], False, "不正なCIDR"],
        [["192.168.1.100-192.168.1.1"], False, "逆順のIP範囲"],
        [["999.999.999.999"], False, "不正なIPアドレス"],
        [["localhost", "10.0.0.0/24", "192.168.1.1-192.168.1.100"], True, "複合設定"],
    ]
    
    for i, (domains, expected_valid, description) in enumerate(test_cases, 1):
        try:
            result = validate_allowed_domains(domains)
            
            if result['valid'] == expected_valid:
                print(f"✅ Validation {i}: {description}")
                if result['errors']:
                    print(f"    エラー: {result['errors']}")
                if result['warnings']:
                    print(f"    警告: {result['warnings']}")
            else:
                print(f"❌ Validation {i}: {description}")
                print(f"    Expected valid: {expected_valid}, Got: {result['valid']}")
                print(f"    Errors: {result['errors']}")
                
        except Exception as e:
            print(f"💥 Validation {i}: {description} - Exception: {e}")


def demo_practical_examples():
    """実用的な例のデモ"""
    print("\n=== 実用例デモ ===\n")
    
    # 実際の企業ネットワーク設定例
    company_allowed = [
        "localhost",
        "127.0.0.1", 
        "company.com",
        ".company.com",          # サブドメイン全て許可
        "10.0.0.0/8",           # 社内ネットワーク
        "192.168.0.0/16",       # VPNネットワーク
        "172.16.1.1-172.16.1.50"  # 特定のサーバー範囲
    ]
    
    demo_referrers = [
        "https://app.company.com/dashboard",
        "http://10.0.5.100/internal",
        "https://vpn.company.com/secure",
        "http://192.168.100.50/admin",
        "http://172.16.1.25/api",
        "https://evil.com/attack",  # 攻撃者
        "http://203.0.113.1/external"  # 外部IP
    ]
    
    print("企業ネットワーク設定例:")
    print("許可設定:", company_allowed)
    print()
    
    for referer in demo_referrers:
        allowed = is_referrer_allowed(referer, company_allowed)
        status = "✅ 許可" if allowed else "❌ 拒否"
        print(f"{status}: {referer}")


if __name__ == "__main__":
    success = test_ip_range_functionality()
    test_validation_functionality()
    demo_practical_examples()
    
    if success:
        print(f"\n🎉 IP範囲チェック機能は正常に動作しています！")
    else:
        print(f"\n⚠️  いくつかのテストで問題が発生しました。")
        sys.exit(1)