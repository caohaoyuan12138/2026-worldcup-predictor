"""
xG 模型训练脚本
使用 StatsBomb Open Data 训练 LightGBM 进球概率预测模型

数据源:
  - FIFA World Cup 2018, 2022 (含 360° freeze-frame)
  - Copa América 2024 (含 360° freeze-frame)
  - UEFA Euro 2024 (含 360° freeze-frame)

输出:
  - model/xg_model/xg_model.json (序列化模型)
  - model/xg_model/feature_importance.json (特征重要性)
  - model/xg_model/evaluation.json (评估指标)
  - data/xg/statsbomb_all_shots.json (训练数据)
"""

import os
import sys
import json
import warnings
import numpy as np
import pandas as pd
from datetime import datetime

from sklearn.model_selection import GroupKFold
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import (
    roc_auc_score, log_loss, brier_score_loss,
    classification_report, precision_recall_curve
)
import lightgbm as lgb

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from features import extract_from_events

warnings.filterwarnings('ignore')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_statsbomb_data():
    """
    从 StatsBomb Open Data 加载所有可用国际大赛的射门事件
    """
    from statsbombpy import sb

    # 定义要加载的赛事
    competitions = [
        # (comp_id, season_id, competition_name, stage_info)
        (43, 106, 'FIFA World Cup 2022', 'mixed'),   # WC 2022 (含 360)
        (43, 3,   'FIFA World Cup 2018', 'mixed'),   # WC 2018
        (617, 282, 'Copa America 2024', 'mixed'),    # Copa 2024 (含 360)
        (55, 282,  'UEFA Euro 2024', 'mixed'),       # Euro 2024 (含 360)
    ]

    all_features = []
    total_shots = 0

    for comp_id, season_id, comp_name, stage_info in competitions:
        print(f"\n{'='*60}")
        print(f"加载: {comp_name}")
        print(f"{'='*60}")

        try:
            # 获取事件数据
            events = sb.events(comp_id=comp_id, season_id=season_id, split=True)
            shots_df = events.get('shots', pd.DataFrame())

            if shots_df.empty:
                print(f"  ⚠️ 没有找到射门数据")
                continue

            print(f"  射门事件数: {len(shots_df)}")

            # 确定比赛阶段
            # 简化：World Cup 以小组赛开始，后期为淘汰赛
            stage = 'group'  # 默认
            if 'knockout' in stage_info.lower() or 'mixed' in stage_info.lower():
                stage = 'mixed'

            # 提取特征
            features = extract_from_events(shots_df, comp_name, stage)
            print(f"  提取特征数: {len(features)}")

            # 添加赛事信息
            for f in features:
                f['competition'] = comp_name

            all_features.extend(features)
            total_shots += len(features)

            # 统计
            goals = sum(1 for f in features if f['is_goal'] == 1)
            print(f"  进球数: {goals}, 进球率: {goals/len(features)*100:.1f}%")

        except Exception as e:
            print(f"  ❌ 加载失败: {e}")
            continue

    print(f"\n{'='*60}")
    print(f"总计: {total_shots} 次射门, {len(all_features)} 条特征")
    print(f"{'='*60}")

    return all_features


def prepare_training_data(features_list):
    """
    准备训练数据

    Returns:
        X: 特征 DataFrame
        y: 标签 Series
        feature_names: 特征名称列表
    """
    df = pd.DataFrame(features_list)

    # 排除点球（点球 xG 约 0.76，单独处理）
    print(f"\n训练数据分布:")
    print(f"  总射门: {len(df)}")
    print(f"  点球: {df['is_penalty'].sum()}")
    print(f"  非点球: {(df['is_penalty'] == 0).sum()}")
    print(f"  进球: {df['is_goal'].sum()}")

    # 移除点球（点球单独建模）
    df_train = df[df['is_penalty'] == 0].copy()
    print(f"\n  训练集（非点球）: {len(df_train)} 次射门")
    print(f"  进球: {df_train['is_goal'].sum()}, 进球率: {df_train['is_goal'].mean()*100:.1f}%")

    # 选择特征列
    feature_cols = [
        # 几何
        'x', 'y', 'distance_to_goal', 'angle_to_goal', 'angle_degrees',
        'visible_goal_angle',

        # 射门类型
        'is_header', 'is_foot', 'is_left_foot', 'is_right_foot',
        'is_free_kick', 'is_corner', 'is_open_play',

        # 技术动作
        'first_time', 'follows_dribble', 'aerial_won',
        'one_on_one', 'open_goal', 'deflect',

        # 360° 防守压力
        'defenders_between', 'gk_distance', 'gk_angle_coverage',

        # 比赛情境
        'minute', 'period', 'is_knockout', 'is_final',
    ]

    X = df_train[feature_cols].copy()
    y = df_train['is_goal'].copy()

    # 处理缺失值
    X = X.fillna(0)

    print(f"\n特征维度: {X.shape[1]}")
    print(f"特征列表: {feature_cols}")

    return X, y, feature_cols


def train_xg_model(X, y, feature_names):
    """
    训练 LightGBM xG 模型 + 概率校准

    Returns:
        model: 校准后的模型
        metrics: 评估指标
    """
    print(f"\n{'='*60}")
    print("训练 xG 模型")
    print(f"{'='*60}")

    # 5-fold 交叉验证
    gkf = GroupKFold(n_splits=5)

    # 创建组标签（按赛事划分，避免数据泄露）
    # 简单：随机分组
    groups = np.arange(len(X)) % 5

    # 基础模型
    base_model = lgb.LGBMClassifier(
        n_estimators=500,
        learning_rate=0.05,
        num_leaves=63,
        max_depth=7,
        min_child_samples=30,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        verbose=-1,
        n_jobs=-1
    )

    # ── 交叉验证评估 ──
    cv_aucs = []
    cv_loglosses = []
    cv_briers = []

    print("\n交叉验证:")
    for fold, (train_idx, val_idx) in enumerate(gkf.split(X, y, groups)):
        X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

        # 训练
        base_model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.early_stopping(50, verbose=False)]
        )

        # 预测
        y_pred = base_model.predict_proba(X_val)[:, 1]

        # 校准
        from sklearn.linear_model import LogisticRegression
        calibrator = LogisticRegression(C=1e10, solver='lbfgs')
        calibrator.fit(y_pred.reshape(-1, 1), y_val)
        y_calibrated = calibrator.predict_proba(y_pred.reshape(-1, 1))[:, 1]

        # 评估
        auc = roc_auc_score(y_val, y_pred)
        ll = log_loss(y_val, y_calibrated)
        bs = brier_score_loss(y_val, y_calibrated)

        cv_aucs.append(auc)
        cv_loglosses.append(ll)
        cv_briers.append(bs)

        print(f"  Fold {fold+1}: AUC={auc:.4f}, LogLoss={ll:.4f}, Brier={bs:.4f}")

    print(f"\n交叉验证平均:")
    print(f"  AUC:      {np.mean(cv_aucs):.4f} ± {np.std(cv_aucs):.4f}")
    print(f"  LogLoss:  {np.mean(cv_loglosses):.4f} ± {np.std(cv_loglosses):.4f}")
    print(f"  Brier:    {np.mean(cv_briers):.4f} ± {np.std(cv_briers):.4f}")

    # ── 全量训练 ──
    print("\n全量训练...")
    base_model.fit(
        X, y,
        callbacks=[lgb.log_evaluation(50)]
    )

    # 概率校准（Isotonic Regression）
    y_pred_full = base_model.predict_proba(X)[:, 1]
    from sklearn.isotonic import IsotonicRegression
    isotonic = IsotonicRegression(y_min=0, y_max=1, out_of_bounds='clip')
    isotonic.fit(y_pred_full, y)

    # ── 特征重要性 ──
    importance = base_model.feature_importances_
    feature_importance = dict(zip(feature_names, importance.tolist()))
    sorted_importance = dict(sorted(feature_importance.items(), key=lambda x: x[1], reverse=True))

    print("\n特征重要性 (Top 15):")
    for i, (feat, imp) in enumerate(list(sorted_importance.items())[:15]):
        bar = '█' * int(imp / max(importance) * 40)
        print(f"  {i+1:2d}. {feat:25s} {imp:6d} {bar}")

    # ── 最终评估 ──
    y_calibrated_full = isotonic.predict(y_pred_full)
    final_auc = roc_auc_score(y, y_pred_full)
    final_logloss = log_loss(y, y_calibrated_full)
    final_brier = brier_score_loss(y, y_calibrated_full)

    metrics = {
        'cv_auc_mean': round(np.mean(cv_aucs), 4),
        'cv_auc_std': round(np.std(cv_aucs), 4),
        'cv_logloss_mean': round(np.mean(cv_loglosses), 4),
        'cv_brier_mean': round(np.mean(cv_briers), 4),
        'final_auc': round(final_auc, 4),
        'final_logloss': round(final_logloss, 4),
        'final_brier': round(final_brier, 4),
        'n_train_samples': len(X),
        'n_features': len(feature_names),
        'positive_rate': round(y.mean(), 4),
    }

    print(f"\n最终评估:")
    print(f"  AUC:      {final_auc:.4f}")
    print(f"  LogLoss:  {final_logloss:.4f}")
    print(f"  Brier:    {final_brier:.4f}")

    # ── 与 StatsBomb xG 对比 ──
    if 'statsbomb_xg' in X.columns or hasattr(X, '_statsbomb_xg'):
        # 注意：statsbomb_xg 是标签，不在特征中
        pass

    model = {
        'base_model': base_model,
        'calibrator': isotonic,
        'feature_names': feature_names,
    }

    return model, metrics, sorted_importance


def save_model(model, metrics, feature_importance, output_dir):
    """
    保存模型和相关文件
    """
    os.makedirs(output_dir, exist_ok=True)

    # 保存 LightGBM 模型
    lgb_path = os.path.join(output_dir, 'xg_lgb_model.txt')
    model['base_model'].booster_.save_model(lgb_path)
    print(f"\n模型保存到: {lgb_path}")

    # 保存校准器
    calibrator = model['calibrator']
    calibrator_data = {
        'X_thresholds': calibrator.X_thresholds_.tolist(),
        'y_thresholds': calibrator.y_thresholds_.tolist(),
    }
    calib_path = os.path.join(output_dir, 'xg_calibrator.json')
    with open(calib_path, 'w') as f:
        json.dump(calibrator_data, f, indent=2)
    print(f"校准器保存到: {calib_path}")

    # 保存特征名称
    config = {
        'feature_names': model['feature_names'],
        'model_type': 'LightGBM + Isotonic Calibration',
        'created_at': datetime.now().isoformat(),
        'penalty_xg': 0.76,  # 点球固定 xG
        'model_paths': {
            'lgb': 'xg_lgb_model.txt',
            'calibrator': 'xg_calibrator.json',
        }
    }
    config_path = os.path.join(output_dir, 'xg_model_config.json')
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"配置保存到: {config_path}")

    # 保存评估指标
    metrics_path = os.path.join(output_dir, 'evaluation.json')
    with open(metrics_path, 'w') as f:
        json.dump(metrics, f, indent=2)
    print(f"评估保存到: {metrics_path}")

    # 保存特征重要性
    importance_path = os.path.join(output_dir, 'feature_importance.json')
    with open(importance_path, 'w') as f:
        json.dump(feature_importance, f, indent=2)
    print(f"特征重要性保存到: {importance_path}")


def main():
    print("=" * 60)
    print("xG 模型训练")
    print(f"时间: {datetime.now().isoformat()}")
    print("=" * 60)

    # 1. 加载数据
    features_list = load_statsbomb_data()

    if not features_list:
        print("❌ 没有加载到任何数据")
        return

    # 保存原始数据
    raw_path = os.path.join(BASE_DIR, 'data', 'xg', 'statsbomb_all_shots.json')
    os.makedirs(os.path.dirname(raw_path), exist_ok=True)
    with open(raw_path, 'w') as f:
        json.dump(features_list, f, ensure_ascii=False)
    print(f"\n原始数据保存到: {raw_path}")

    # 2. 准备训练数据
    X, y, feature_names = prepare_training_data(features_list)

    # 3. 训练模型
    model, metrics, importance = train_xg_model(X, y, feature_names)

    # 4. 保存模型
    output_dir = os.path.join(BASE_DIR, 'model', 'xg_model')
    save_model(model, metrics, importance, output_dir)

    print(f"\n{'='*60}")
    print("✅ xG 模型训练完成!")
    print(f"{'='*60}")
    print(f"模型目录: {output_dir}")
    print(f"训练样本: {metrics['n_train_samples']}")
    print(f"AUC: {metrics['final_auc']}")
    print(f"LogLoss: {metrics['final_logloss']}")
    print(f"Brier: {metrics['final_brier']}")


if __name__ == '__main__':
    main()
