# engine/scoring.py
import pandas as pd
import numpy as np

class CompatibilityEngine:
    def __init__(self, weights: dict):
        self.weights = weights

    def compute_matrix(self, df_students: pd.DataFrame) -> np.ndarray:
        n = len(df_students)
        matrix = np.zeros((n, n))
        records = df_students.to_dict(orient='records')
        
        for i in range(n):
            for j in range(i + 1, n):
                score = 0
                s1, s2 = records[i], records[j]
                
                # 1. Cleanliness Matching (Binary 1 or 0 matching is crucial)
                if s1['cleanliness'] == s2['cleanliness']:
                    score += self.weights.get('cleanliness', 40)
                else:
                    score -= self.weights.get('cleanliness', 40) * 0.5
                
                # 2. Noise & Study Environment Alignment
                if s1['noise_tolerance'] == s2['noise_tolerance']:
                    score += self.weights.get('noise', 30)
                if s1['study_habit'] == s2['study_habit']:
                    score += self.weights.get('study', 30)
                
                # 3. Sleep & Wake Schedules
                if s1['sleep_window'] == s2['sleep_window']:
                    score += self.weights.get('schedule', 20)
                if s1['wake_window'] == s2['wake_window']:
                    score += self.weights.get('schedule', 20)
                    
                # 4. Optional Peer Multiplier: Common Faculty/Major (soft bonus)
                if s1['faculty'] == s2['faculty']:
                    score += 10
                
                # 5. Cultural/Sect Safety Constraint (Hard Boundary Filter)
                if s1['cultural_group'] != s2['cultural_group']:
                    score -= 1000  # Strong negative force to isolate distinct classes
                
                matrix[i][j] = score
                matrix[j][i] = score
                
        return matrix