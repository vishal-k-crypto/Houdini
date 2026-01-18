#!/usr/bin/env python3
"""
Training Data Viability Checklist
==================================
Analyzes replay sessions to determine if data is suitable for training ML executor models.
"""

import json
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Tuple
from datetime import datetime


class TrainingDataChecker:
    """Comprehensive checklist for ML training data viability."""
    
    def __init__(self, sessions_dir: str = "data/replay_sessions"):
        self.sessions_dir = Path(sessions_dir)
        self.screenshots_dir = Path("data/screenshots")
        
    def analyze_all_sessions(self) -> Dict:
        """Run complete viability analysis on all sessions."""
        
        # Load all completed sessions (not .live.jsonl)
        sessions = []
        for file in self.sessions_dir.glob("*.json"):
            if ".live" not in file.name:
                try:
                    with open(file) as f:
                        data = json.load(f)
                        sessions.append((file.name, data))
                except:
                    pass
        
        print(f"\n{'='*80}")
        print(f"ML TRAINING DATA VIABILITY CHECKLIST")
        print(f"{'='*80}")
        print(f"Analyzing {len(sessions)} completed sessions...")
        print(f"{'='*80}\n")
        
        # Run all checks
        results = {
            "total_sessions": len(sessions),
            "checks": {}
        }
        
        results["checks"]["1_screenshot_coverage"] = self._check_screenshot_coverage(sessions)
        results["checks"]["2_action_diversity"] = self._check_action_diversity(sessions)
        results["checks"]["3_success_rate"] = self._check_success_rate(sessions)
        results["checks"]["4_data_completeness"] = self._check_data_completeness(sessions)
        results["checks"]["5_temporal_consistency"] = self._check_temporal_consistency(sessions)
        results["checks"]["6_state_action_pairs"] = self._check_state_action_pairs(sessions)
        results["checks"]["7_failure_modes"] = self._check_failure_modes(sessions)
        results["checks"]["8_task_distribution"] = self._check_task_distribution(sessions)
        results["checks"]["9_dataset_size"] = self._check_dataset_size(sessions)
        results["checks"]["10_label_quality"] = self._check_label_quality(sessions)
        
        # Calculate overall viability score
        results["overall_viability"] = self._calculate_viability_score(results["checks"])
        
        # Print final verdict
        self._print_verdict(results["overall_viability"])
        
        return results
    
    def _check_screenshot_coverage(self, sessions: List[Tuple]) -> Dict:
        """✓ CHECK 1: Screenshot Coverage - Do we have visual state for actions?"""
        print("\n[1/10] SCREENSHOT COVERAGE")
        print("-" * 80)
        
        total_actions = 0
        actions_with_screenshots = 0
        missing_files = 0
        
        for filename, data in sessions:
            for event in data.get("events", []):
                if event.get("event_type") in ["action_start", "action_success"]:
                    total_actions += 1
                    screenshot_path = event.get("screenshot_path")
                    
                    if screenshot_path:
                        actions_with_screenshots += 1
                        # Verify file exists
                        if not Path(screenshot_path).exists():
                            missing_files += 1
        
        coverage = (actions_with_screenshots / total_actions * 100) if total_actions > 0 else 0
        
        result = {
            "total_actions": total_actions,
            "actions_with_screenshots": actions_with_screenshots,
            "coverage_percent": round(coverage, 1),
            "missing_files": missing_files,
            "status": "✅ PASS" if coverage >= 90 else "⚠️  WARN" if coverage >= 60 else "❌ FAIL"
        }
        
        print(f"Total Actions: {total_actions}")
        print(f"Actions with Screenshots: {actions_with_screenshots} ({result['coverage_percent']}%)")
        print(f"Missing Screenshot Files: {missing_files}")
        print(f"Status: {result['status']}")
        print(f"Requirement: ≥90% for PASS, ≥60% for WARN")
        
        return result
    
    def _check_action_diversity(self, sessions: List[Tuple]) -> Dict:
        """✓ CHECK 2: Action Diversity - Do we have varied action types?"""
        print("\n[2/10] ACTION DIVERSITY")
        print("-" * 80)
        
        action_types = Counter()
        action_descriptions = set()
        
        for filename, data in sessions:
            for event in data.get("events", []):
                if event.get("event_type") == "action_start":
                    action_type = event.get("data", {}).get("action_type", "unknown")
                    action_types[action_type] += 1
                    action_descriptions.add(event.get("data", {}).get("action", "")[:50])
        
        unique_types = len(action_types)
        unique_descriptions = len(action_descriptions)
        
        result = {
            "unique_action_types": unique_types,
            "unique_descriptions": unique_descriptions,
            "action_type_distribution": dict(action_types.most_common(10)),
            "status": "✅ PASS" if unique_types >= 8 else "⚠️  WARN" if unique_types >= 5 else "❌ FAIL"
        }
        
        print(f"Unique Action Types: {unique_types}")
        print(f"Unique Action Descriptions: {unique_descriptions}")
        print(f"\nTop Action Types:")
        for action_type, count in action_types.most_common(5):
            print(f"  • {action_type}: {count}")
        print(f"\nStatus: {result['status']}")
        print(f"Requirement: ≥8 types for PASS, ≥5 for WARN")
        
        return result
    
    def _check_success_rate(self, sessions: List[Tuple]) -> Dict:
        """✓ CHECK 3: Success Rate - Are tasks completing successfully?"""
        print("\n[3/10] TASK SUCCESS RATE")
        print("-" * 80)
        
        total = len(sessions)
        successful = 0
        failed = 0
        partial = 0
        
        for filename, data in sessions:
            status = data.get("summary", {}).get("task_status", "failed")
            if status == "success":
                successful += 1
            elif status == "partial_success":
                partial += 1
            else:
                failed += 1
        
        success_rate = (successful / total * 100) if total > 0 else 0
        
        result = {
            "total_sessions": total,
            "successful": successful,
            "partial": partial,
            "failed": failed,
            "success_rate_percent": round(success_rate, 1),
            "status": "✅ PASS" if success_rate >= 40 else "⚠️  WARN" if success_rate >= 20 else "❌ FAIL"
        }
        
        print(f"Total Sessions: {total}")
        print(f"Successful: {successful} ({result['success_rate_percent']}%)")
        print(f"Partial Success: {partial}")
        print(f"Failed: {failed}")
        print(f"\nStatus: {result['status']}")
        print(f"Requirement: ≥40% for PASS, ≥20% for WARN")
        print(f"Note: Failed sessions still provide valuable negative examples")
        
        return result
    
    def _check_data_completeness(self, sessions: List[Tuple]) -> Dict:
        """✓ CHECK 4: Data Completeness - Are all required fields present?"""
        print("\n[4/10] DATA COMPLETENESS")
        print("-" * 80)
        
        required_fields = ["task_id", "task_description", "started_at", "events"]
        incomplete_sessions = 0
        missing_timestamps = 0
        missing_cursors = 0
        
        for filename, data in sessions:
            # Check session-level fields
            if not all(field in data for field in required_fields):
                incomplete_sessions += 1
                continue
            
            # Check event-level fields
            for event in data.get("events", []):
                if "timestamp_ms" not in event or "relative_ms" not in event:
                    missing_timestamps += 1
                if "cursor_x" not in event or "cursor_y" not in event:
                    missing_cursors += 1
        
        completeness = ((len(sessions) - incomplete_sessions) / len(sessions) * 100) if sessions else 0
        
        result = {
            "total_sessions": len(sessions),
            "incomplete_sessions": incomplete_sessions,
            "missing_timestamps": missing_timestamps,
            "missing_cursor_data": missing_cursors,
            "completeness_percent": round(completeness, 1),
            "status": "✅ PASS" if completeness >= 95 else "⚠️  WARN" if completeness >= 80 else "❌ FAIL"
        }
        
        print(f"Complete Sessions: {len(sessions) - incomplete_sessions}/{len(sessions)} ({result['completeness_percent']}%)")
        print(f"Missing Timestamps: {missing_timestamps} events")
        print(f"Missing Cursor Data: {missing_cursors} events")
        print(f"\nStatus: {result['status']}")
        print(f"Requirement: ≥95% for PASS, ≥80% for WARN")
        
        return result
    
    def _check_temporal_consistency(self, sessions: List[Tuple]) -> Dict:
        """✓ CHECK 5: Temporal Consistency - Are timestamps monotonic and reasonable?"""
        print("\n[5/10] TEMPORAL CONSISTENCY")
        print("-" * 80)
        
        inconsistent_sessions = 0
        time_gaps = []
        
        for filename, data in sessions:
            events = data.get("events", [])
            if len(events) < 2:
                continue
            
            prev_time = 0
            consistent = True
            
            for event in events:
                current_time = event.get("relative_ms", 0)
                
                # Check monotonic increase
                if current_time < prev_time:
                    consistent = False
                    break
                
                # Track gaps between events
                if prev_time > 0:
                    gap = current_time - prev_time
                    if gap > 0:
                        time_gaps.append(gap)
                
                prev_time = current_time
            
            if not consistent:
                inconsistent_sessions += 1
        
        consistency = ((len(sessions) - inconsistent_sessions) / len(sessions) * 100) if sessions else 0
        avg_gap = sum(time_gaps) / len(time_gaps) if time_gaps else 0
        
        result = {
            "total_sessions": len(sessions),
            "inconsistent_sessions": inconsistent_sessions,
            "consistency_percent": round(consistency, 1),
            "avg_event_gap_ms": round(avg_gap, 1),
            "status": "✅ PASS" if consistency >= 98 else "⚠️  WARN" if consistency >= 90 else "❌ FAIL"
        }
        
        print(f"Consistent Sessions: {len(sessions) - inconsistent_sessions}/{len(sessions)} ({result['consistency_percent']}%)")
        print(f"Average Event Gap: {result['avg_event_gap_ms']}ms")
        print(f"\nStatus: {result['status']}")
        print(f"Requirement: ≥98% for PASS, ≥90% for WARN")
        
        return result
    
    def _check_state_action_pairs(self, sessions: List[Tuple]) -> Dict:
        """✓ CHECK 6: State-Action Pairs - Do we have valid (state, action, outcome) tuples?"""
        print("\n[6/10] STATE-ACTION PAIRS")
        print("-" * 80)
        
        valid_pairs = 0
        total_actions = 0
        pairs_with_outcome = 0
        
        for filename, data in sessions:
            events = data.get("events", [])
            
            for i, event in enumerate(events):
                if event.get("event_type") == "action_start":
                    total_actions += 1
                    
                    # Check if we have screenshot (state)
                    has_state = bool(event.get("screenshot_path"))
                    
                    # Check if we have action details
                    has_action = bool(event.get("data", {}).get("action"))
                    
                    # Check if we have outcome (next event should be success/failure)
                    has_outcome = False
                    if i + 1 < len(events):
                        next_event = events[i + 1]
                        if next_event.get("event_type") in ["action_success", "action_failed"]:
                            has_outcome = True
                            pairs_with_outcome += 1
                    
                    if has_state and has_action:
                        valid_pairs += 1
        
        pair_quality = (valid_pairs / total_actions * 100) if total_actions > 0 else 0
        outcome_coverage = (pairs_with_outcome / total_actions * 100) if total_actions > 0 else 0
        
        result = {
            "total_actions": total_actions,
            "valid_state_action_pairs": valid_pairs,
            "pairs_with_outcome": pairs_with_outcome,
            "pair_quality_percent": round(pair_quality, 1),
            "outcome_coverage_percent": round(outcome_coverage, 1),
            "status": "✅ PASS" if pair_quality >= 85 else "⚠️  WARN" if pair_quality >= 60 else "❌ FAIL"
        }
        
        print(f"Total Actions: {total_actions}")
        print(f"Valid (State, Action) Pairs: {valid_pairs} ({result['pair_quality_percent']}%)")
        print(f"Pairs with Outcomes: {pairs_with_outcome} ({result['outcome_coverage_percent']}%)")
        print(f"\nStatus: {result['status']}")
        print(f"Requirement: ≥85% for PASS, ≥60% for WARN")
        
        return result
    
    def _check_failure_modes(self, sessions: List[Tuple]) -> Dict:
        """✓ CHECK 7: Failure Modes - Do we capture diverse failure scenarios?"""
        print("\n[7/10] FAILURE MODE DIVERSITY")
        print("-" * 80)
        
        error_types = Counter()
        total_failures = 0
        
        for filename, data in sessions:
            for event in data.get("events", []):
                if event.get("event_type") == "action_failed":
                    total_failures += 1
                    error = event.get("data", {}).get("error", "unknown")
                    # Simplify error messages to categories
                    if "timeout" in error.lower():
                        error_types["timeout"] += 1
                    elif "not found" in error.lower():
                        error_types["element_not_found"] += 1
                    elif "attribute" in error.lower():
                        error_types["attribute_error"] += 1
                    else:
                        error_types["other"] += 1
        
        unique_errors = len(error_types)
        
        result = {
            "total_failures": total_failures,
            "unique_error_types": unique_errors,
            "error_distribution": dict(error_types.most_common(5)),
            "status": "✅ PASS" if unique_errors >= 3 else "⚠️  WARN" if unique_errors >= 2 else "❌ FAIL"
        }
        
        print(f"Total Failures: {total_failures}")
        print(f"Unique Error Types: {unique_errors}")
        if error_types:
            print(f"\nError Distribution:")
            for error_type, count in error_types.most_common(5):
                print(f"  • {error_type}: {count}")
        print(f"\nStatus: {result['status']}")
        print(f"Requirement: ≥3 types for PASS, ≥2 for WARN")
        print(f"Note: Failures help model learn what NOT to do")
        
        return result
    
    def _check_task_distribution(self, sessions: List[Tuple]) -> Dict:
        """✓ CHECK 8: Task Distribution - Do we have diverse task types?"""
        print("\n[8/10] TASK TYPE DISTRIBUTION")
        print("-" * 80)
        
        task_keywords = defaultdict(int)
        unique_tasks = set()
        
        for filename, data in sessions:
            task = data.get("task_description", "").lower()
            unique_tasks.add(task)
            
            # Categorize by keywords
            if "search" in task or "find" in task:
                task_keywords["search"] += 1
            if "download" in task:
                task_keywords["download"] += 1
            if "navigate" in task or "go to" in task:
                task_keywords["navigation"] += 1
            if "click" in task:
                task_keywords["clicking"] += 1
            if "type" in task or "enter" in task:
                task_keywords["typing"] += 1
            if "open" in task or "launch" in task:
                task_keywords["app_launch"] += 1
        
        unique_count = len(unique_tasks)
        categories = len(task_keywords)
        
        result = {
            "total_sessions": len(sessions),
            "unique_tasks": unique_count,
            "task_categories": categories,
            "category_distribution": dict(task_keywords),
            "status": "✅ PASS" if categories >= 4 else "⚠️  WARN" if categories >= 2 else "❌ FAIL"
        }
        
        print(f"Unique Tasks: {unique_count}")
        print(f"Task Categories: {categories}")
        print(f"\nCategory Distribution:")
        for category, count in sorted(task_keywords.items(), key=lambda x: -x[1]):
            print(f"  • {category}: {count}")
        print(f"\nStatus: {result['status']}")
        print(f"Requirement: ≥4 categories for PASS, ≥2 for WARN")
        
        return result
    
    def _check_dataset_size(self, sessions: List[Tuple]) -> Dict:
        """✓ CHECK 9: Dataset Size - Do we have enough data for training?"""
        print("\n[9/10] DATASET SIZE")
        print("-" * 80)
        
        total_sessions = len(sessions)
        total_actions = 0
        total_screenshots = 0
        
        for filename, data in sessions:
            for event in data.get("events", []):
                if event.get("event_type") in ["action_start", "action_success"]:
                    total_actions += 1
                if event.get("screenshot_path"):
                    total_screenshots += 1
        
        # Calculate disk usage
        total_size_mb = 0
        if self.screenshots_dir.exists():
            for img in self.screenshots_dir.glob("*.png"):
                total_size_mb += img.stat().st_size / (1024 * 1024)
        
        result = {
            "total_sessions": total_sessions,
            "total_actions": total_actions,
            "total_screenshots": total_screenshots,
            "dataset_size_mb": round(total_size_mb, 1),
            "status": "✅ PASS" if total_sessions >= 100 else "⚠️  WARN" if total_sessions >= 20 else "❌ FAIL",
            "recommendation": self._get_size_recommendation(total_sessions)
        }
        
        print(f"Total Sessions: {total_sessions}")
        print(f"Total Actions: {total_actions}")
        print(f"Total Screenshots: {total_screenshots}")
        print(f"Dataset Size: {result['dataset_size_mb']} MB")
        print(f"\nStatus: {result['status']}")
        print(f"Requirement: ≥100 sessions for PASS, ≥20 for WARN")
        print(f"\nRecommendation: {result['recommendation']}")
        
        return result
    
    def _get_size_recommendation(self, sessions: int) -> str:
        """Get recommendation based on dataset size."""
        if sessions < 20:
            return "Need 100x more data. Start Docker 24/7 collection immediately."
        elif sessions < 100:
            return "Need 5-10x more data. Continue automated collection."
        elif sessions < 1000:
            return "Good start. Can train proof-of-concept. Aim for 1000+ sessions."
        elif sessions < 10000:
            return "Good dataset. Can train useful model. For production: aim for 10k+."
        else:
            return "Excellent dataset size! Ready for serious model training."
    
    def _check_label_quality(self, sessions: List[Tuple]) -> Dict:
        """✓ CHECK 10: Label Quality - Are action labels clear and consistent?"""
        print("\n[10/10] LABEL QUALITY")
        print("-" * 80)
        
        total_actions = 0
        labeled_actions = 0
        has_action_type = 0
        has_confidence = 0
        
        for filename, data in sessions:
            for event in data.get("events", []):
                if event.get("event_type") == "action_start":
                    total_actions += 1
                    
                    action_data = event.get("data", {})
                    if action_data.get("action"):
                        labeled_actions += 1
                    if action_data.get("action_type"):
                        has_action_type += 1
                    if "confidence" in action_data or "confidence_score" in action_data:
                        has_confidence += 1
        
        label_quality = (labeled_actions / total_actions * 100) if total_actions > 0 else 0
        type_coverage = (has_action_type / total_actions * 100) if total_actions > 0 else 0
        
        result = {
            "total_actions": total_actions,
            "labeled_actions": labeled_actions,
            "has_action_type": has_action_type,
            "has_confidence_score": has_confidence,
            "label_quality_percent": round(label_quality, 1),
            "type_coverage_percent": round(type_coverage, 1),
            "status": "✅ PASS" if label_quality >= 95 else "⚠️  WARN" if label_quality >= 80 else "❌ FAIL"
        }
        
        print(f"Total Actions: {total_actions}")
        print(f"Actions with Labels: {labeled_actions} ({result['label_quality_percent']}%)")
        print(f"Actions with Type: {has_action_type} ({result['type_coverage_percent']}%)")
        print(f"Actions with Confidence: {has_confidence}")
        print(f"\nStatus: {result['status']}")
        print(f"Requirement: ≥95% for PASS, ≥80% for WARN")
        
        return result
    
    def _calculate_viability_score(self, checks: Dict) -> Dict:
        """Calculate overall viability score based on all checks."""
        
        # Weight for each check (sum = 100)
        weights = {
            "1_screenshot_coverage": 20,      # Most critical
            "2_action_diversity": 10,
            "3_success_rate": 8,
            "4_data_completeness": 12,
            "5_temporal_consistency": 5,
            "6_state_action_pairs": 20,       # Very important
            "7_failure_modes": 5,
            "8_task_distribution": 8,
            "9_dataset_size": 10,
            "10_label_quality": 12
        }
        
        total_score = 0
        max_score = 0
        
        for check_name, weight in weights.items():
            check_result = checks.get(check_name, {})
            status = check_result.get("status", "")
            
            # Assign points based on status
            if "✅" in status:
                points = weight
            elif "⚠️" in status:
                points = weight * 0.6
            else:  # ❌ FAIL
                points = weight * 0.2
            
            total_score += points
            max_score += weight
        
        percentage = (total_score / max_score * 100) if max_score > 0 else 0
        
        return {
            "score": round(total_score, 1),
            "max_score": max_score,
            "percentage": round(percentage, 1),
            "grade": self._get_grade(percentage)
        }
    
    def _get_grade(self, percentage: float) -> str:
        """Get letter grade based on percentage."""
        if percentage >= 90:
            return "A - Excellent"
        elif percentage >= 80:
            return "B - Good"
        elif percentage >= 70:
            return "C - Acceptable"
        elif percentage >= 60:
            return "D - Poor"
        else:
            return "F - Inadequate"
    
    def _print_verdict(self, viability: Dict):
        """Print final verdict on training viability."""
        print(f"\n{'='*80}")
        print(f"FINAL VERDICT")
        print(f"{'='*80}")
        print(f"Overall Score: {viability['score']}/{viability['max_score']} ({viability['percentage']}%)")
        print(f"Grade: {viability['grade']}")
        print(f"{'='*80}")
        
        percentage = viability['percentage']
        
        if percentage >= 85:
            print("✅ READY FOR TRAINING")
            print("This dataset is suitable for training ML executor models.")
            print("Recommended: Start with supervised learning (imitation learning).")
        elif percentage >= 70:
            print("⚠️  MARGINALLY VIABLE")
            print("Dataset can be used but has quality issues.")
            print("Recommended: Fix issues before investing in expensive training.")
        elif percentage >= 50:
            print("⚠️  NOT RECOMMENDED")
            print("Significant quality issues. Training likely to produce poor results.")
            print("Recommended: Improve data collection pipeline first.")
        else:
            print("❌ NOT VIABLE")
            print("Critical quality issues. Do NOT proceed with training.")
            print("Recommended: Fix data collection before gathering more data.")
        
        print(f"{'='*80}\n")


def main():
    """Run the training viability checker."""
    checker = TrainingDataChecker()
    results = checker.analyze_all_sessions()
    
    # Save results to file
    output_file = Path("data/training_viability_report.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"📊 Full report saved to: {output_file}")


if __name__ == "__main__":
    main()
