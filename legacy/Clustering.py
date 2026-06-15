"""Deprecated clustering experiment. Production code must not import this."""

import os
os.environ['OMP_NUM_THREADS'] = '4'

import numpy as np
import pandas as pd
import optuna
from sklearn.cluster import KMeans, AgglomerativeClustering, DBSCAN
from sklearn.mixture import GaussianMixture
from sklearn.metrics import calinski_harabasz_score, davies_bouldin_score, silhouette_score
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler


def run_clustering(
	input_csv: str,
	output_csv: str = "MOCK_DATA-Women.csv",
	n_trials: int = 200,
	k_mode: str = "auto",
	specified_k: int = 20,
	min_k: int = 25,
	max_k: int = 125,
) -> dict:
	"""Run Optuna-tuned clustering on a CSV and write labeled output.

	Returns a dict with keys: best_params, best_value, silhouette (optional), output_csv
	"""
	df = pd.read_csv(input_csv)
	X = df.select_dtypes(include=np.number).values

	def objective(trial):
		use_scaler = trial.suggest_categorical("use_scaler", [True, False])
		use_pca = trial.suggest_categorical("use_pca", [True, False])
		pca_components = (
			trial.suggest_int("pca_components", 5, min(50, X.shape[1])) if use_pca else None
		)

		X_proc = X.copy()
		if use_scaler:
			X_proc = StandardScaler().fit_transform(X_proc)
		if use_pca:
			X_proc = PCA(n_components=pca_components).fit_transform(X_proc)

		algo = trial.suggest_categorical("algorithm", ["kmeans", "agglomerative", "gmm", "dbscan"])

		if algo in ["kmeans", "agglomerative", "gmm"]:
			if k_mode == "auto":
				n_clusters = trial.suggest_int("n_clusters", min_k, max_k)
			else:
				n_clusters = specified_k

		if algo == "kmeans":
			model = KMeans(n_clusters=n_clusters, n_init="auto")
			labels = model.fit_predict(X_proc)
		elif algo == "agglomerative":
			linkage = trial.suggest_categorical("linkage", ["ward", "complete", "average", "single"])
			model = AgglomerativeClustering(n_clusters=n_clusters, linkage=linkage)
			labels = model.fit_predict(X_proc)
		elif algo == "gmm":
			model = GaussianMixture(n_components=n_clusters)
			labels = model.fit_predict(X_proc)
		else:
			eps = trial.suggest_float("eps", 0.1, 10.0, log=True)
			min_samples = trial.suggest_int("min_samples", 3, 20)
			model = DBSCAN(eps=eps, min_samples=min_samples)
			labels = model.fit_predict(X_proc)
			if len(np.unique(labels)) < 2:
				return -1e6

		ch_score = calinski_harabasz_score(X_proc, labels)
		db_score = davies_bouldin_score(X_proc, labels)
		return ch_score - db_score * 100

	study = optuna.create_study(direction="maximize")
	study.optimize(objective, n_trials=int(n_trials))

	best = study.best_params
	X_proc = X.copy()
	if best.get("use_scaler", False):
		X_proc = StandardScaler().fit_transform(X_proc)
	if best.get("use_pca", False):
		X_proc = PCA(n_components=best["pca_components"]).fit_transform(X_proc)

	algo = best["algorithm"]
	if algo == "kmeans":
		model = KMeans(n_clusters=best["n_clusters"], n_init="auto")
		labels = model.fit_predict(X_proc)
	elif algo == "agglomerative":
		model = AgglomerativeClustering(n_clusters=best["n_clusters"], linkage=best["linkage"])
		labels = model.fit_predict(X_proc)
	elif algo == "gmm":
		model = GaussianMixture(n_components=best["n_clusters"])
		labels = model.fit_predict(X_proc)
	else:
		model = DBSCAN(eps=best["eps"], min_samples=best["min_samples"])
		labels = model.fit_predict(X_proc)

	result = {
		"best_params": best,
		"best_value": study.best_value,
		"output_csv": output_csv,
	}
	if len(np.unique(labels)) > 1:
		result["silhouette"] = float(silhouette_score(X_proc, labels))

	# Save labeled output
	df_out = pd.read_csv(output_csv)
	df_out["Cluster"] = labels
	df_out.to_csv(f"{output_csv}_labeled.csv", index=False)
	return result


if __name__ == "__main__":
	# Simple CLI for ad-hoc runs
	input_path = os.environ.get("INPUT_CSV", "EncodedWomen_english.csv")
	output_path = os.environ.get("OUTPUT_CSV", "LabeledWomen.csv")
	info = run_clustering(input_path, output_path)
	print("Best Params:", info["best_params"])
	print("Best Combined Score:", info["best_value"]) 
	print("Output:", info["output_csv"]) 
