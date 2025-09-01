#!/usr/bin/env python3
"""
PDF セキュリティ設定を環境変数からデータベースに反映するスクリプト
"""
import os
import json
from dotenv import load_dotenv
from config.pdf_security_settings import get_pdf_security_config, set_pdf_security_config


def main():
    print("=== PDF セキュリティ設定の更新 ===\n")
    
    # 環境変数を読み込み
    load_dotenv()
    print("✅ .envファイルを読み込みました")
    
    # 環境変数から設定を取得
    env_config = {
        'enabled': os.getenv('PDF_DOWNLOAD_PREVENTION_ENABLED', 'true').lower() == 'true',
        'allowed_referrer_domains': os.getenv('PDF_ALLOWED_REFERRER_DOMAINS', 'localhost,127.0.0.1'),
        'blocked_user_agents': os.getenv('PDF_BLOCKED_USER_AGENTS', 'wget,curl,python-requests'),
        'strict_mode': os.getenv('PDF_STRICT_MODE', 'false').lower() == 'true',
        'log_blocked_attempts': os.getenv('PDF_LOG_BLOCKED_ATTEMPTS', 'true').lower() == 'true',
        'user_agent_check_enabled': os.getenv('PDF_USER_AGENT_CHECK_ENABLED', 'true').lower() == 'true'
    }
    
    print("📋 環境変数からの設定:")
    print(json.dumps(env_config, indent=2, ensure_ascii=False))
    print()
    
    # データベースに反映
    print("💾 データベースに設定を反映中...")
    success = set_pdf_security_config(env_config, 'env_update_script')
    
    if success:
        print("✅ 設定をデータベースに反映しました")
    else:
        print("❌ 設定の反映に失敗しました")
        return 1
    
    # 更新後の設定を確認
    print("\n🔍 更新後のデータベース設定:")
    updated_config = get_pdf_security_config()
    print(json.dumps(updated_config, indent=2, ensure_ascii=False))
    
    # 設定サマリー
    print(f"\n📊 設定サマリー:")
    print(f"・機能有効: {'✅' if updated_config.get('enabled') else '❌'}")
    print(f"・User-Agentチェック: {'✅' if updated_config.get('user_agent_check_enabled') else '❌'}")
    
    # 許可ドメインの表示
    domains = updated_config.get('allowed_referrer_domains', '')
    if isinstance(domains, str):
        domain_list = [d.strip() for d in domains.split(',') if d.strip()]
    else:
        domain_list = domains if isinstance(domains, list) else []
    print(f"・許可ドメイン: {len(domain_list)}件")
    
    # ブロックUAの表示
    agents = updated_config.get('blocked_user_agents', '')
    if isinstance(agents, str):
        agent_list = [a.strip() for a in agents.split(',') if a.strip()]
    else:
        agent_list = agents if isinstance(agents, list) else []
    print(f"・ブロックUA: {len(agent_list)}件")
    
    print(f"\n🎉 PDF セキュリティ設定の更新が完了しました！")
    print(f"管理画面（http://your-domain/admin）で詳細を確認できます。")
    
    return 0


if __name__ == "__main__":
    exit(main())