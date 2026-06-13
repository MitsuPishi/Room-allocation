# An AI-based Roommate Matching System for University Dormitories

A comprehensive Streamlit application for university administrators to analyze student clustering results, allocate dormitory rooms, and explore student data through interactive visualizations.

## Features

###  Data Analysis & Visualization
- **Interactive Clustering Exploration**: Upload CSV files or use existing datasets
- **2D Projections**: PCA and t-SNE visualizations with customizable feature selection
- **Cluster Analysis**: Bar charts, scatter plots, and statistical summaries
- **Flexible Data Types**: Option to treat numeric columns as categorical for better visualization
- **Advanced Filtering**: Search across all columns and filter by cluster groups

###  Dormitory Room Allocation
- **Smart Room Assignment**: Multiple allocation policies (homogeneous, diverse, random)
- **Configurable Capacity**: Adjustable room sizes (2-12 students)
- **Visual Room Composition**: Stacked bar charts showing cluster distribution per room
- **Homogeneity Analysis**: Histograms showing room diversity metrics
- **Room & Student Search**: Find specific rooms or search for individual students

###  Advanced Search & Discovery
- **Multi-Column Search**: Search across all student attributes
- **Room Details**: View complete student information for any room
- **Column Visibility**: Toggle display of specific student fields
- **Export Capabilities**: Download filtered data and room assignments

###  Automated Clustering
- **Optuna-Optimized Clustering**: Automated hyperparameter tuning
- **Multiple Algorithms**: K-Means, Agglomerative, Gaussian Mixture, DBSCAN
- **Flexible Configuration**: Auto or fixed cluster count selection
- **Performance Metrics**: Silhouette score, Calinski-Harabasz, Davies-Bouldin

## Demo
Here is an example of the app in action:

**Dashboard Preview:**

![Dashboard Example](Docs/Images/Overview.png)

**Clustering Visualization:**

![Cluster Plot](Docs/Images/Clustering.png)

**Final Room Allocation Table:**

![Room Allocation](Docs/Images/Allocation.png)


##  Requirements

- Python 3.9–3.12
- See `requirements.txt` for complete package list

##  Installation

### Windows PowerShell
```powershell
git clone https://github.com/DarkCube-team/UniMate
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Linux/macOS
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

##  Quick Start

1. **Prepare your data**: Place Student data (One hot encoded) in the Data Directory, or upload via the app
2. **Launch the application**:
   ```bash
   streamlit run app.py
   ```
3. **Open your browser** to `http://localhost:8501`

##  Usage Guide

### Data Upload & Configuration
- Use the sidebar to upload CSV files or specify existing files
- Select the cluster label column (auto-detection available)
- Choose visualization settings and feature selections

### Room Allocation Workflow
1. Configure room capacity and allocation policy in the sidebar
2. Select student identifier column
3. View room composition charts and homogeneity analysis
4. Use search tools to find specific rooms or students
5. Toggle column visibility to focus on relevant student information

### Running Custom Clustering
1. Navigate to "Run clustering on a CSV and visualize the result"
2. Upload input data or specify filename
3. Configure Optuna trials and cluster parameters
4. Execute clustering and download labeled results
5. Use labeled output in main dashboard sections

##  Configuration Options

### Clustering Parameters
- **Trials**: 10-1000 Optuna optimization trials
- **K Selection**: Auto (min/max range) or fixed cluster count
- **Algorithms**: K-Means, Agglomerative, Gaussian Mixture, DBSCAN
- **Preprocessing**: Optional scaling and PCA dimensionality reduction

### Room Allocation Policies
- **Pack by Cluster**: Maximizes within-room homogeneity
- **Round-Robin**: Distributes clusters evenly across rooms
- **Random Shuffle**: Unbiased random assignment

### Visualization Settings
- **Projection Methods**: PCA (fast) or t-SNE (detailed)
- **Feature Selection**: Choose numeric features for 2D projections
- **Categorical Override**: Treat numeric columns as categories
- **Column Visibility**: Customize displayed student information

##  Future Improvements

### Phase 1: Enhanced Analytics
- [ ] **Advanced Clustering Metrics**: Additional validation indices and stability analysis
- [ ] **Time Series Analysis**: Track student cluster evolution over semesters
- [ ] **Predictive Modeling**: Roommate compatibility scoring based on historical data
- [ ] **Interactive Heatmaps**: Correlation matrices and feature importance visualizations

### Phase 2: User Experience
- [ ] **User Authentication**: Role-based access control for different university departments
- [ ] **Saved Configurations**: Preserve user preferences and analysis settings
- [ ] **Bulk Operations**: Mass room reassignments and batch processing
- [ ] **Mobile Responsiveness**: Optimized interface for tablet and mobile devices

### Phase 3: Integration & Automation
- [ ] **Database Integration**: Direct connection to university student information systems
- [ ] **API Endpoints**: RESTful API for programmatic access and integration
- [ ] **Automated Scheduling**: Periodic clustering updates and room reallocation
- [ ] **Notification System**: Alerts for room changes and important updates

### Phase 4: Advanced Features
- [ ] **Machine Learning Pipeline**: Automated feature engineering and model selection
- [ ] **Real-time Updates**: Live data synchronization and instant visualization updates
- [ ] **Multi-campus Support**: Handle multiple university locations and cross-campus analysis
- [ ] **Advanced Reporting**: PDF report generation with customizable templates

##  Contributing

We welcome contributions , if you are interested in improving the performance or have any ideas feel free to contact us or open an issue!

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

##  Performance Notes

- **Large Datasets**: For datasets >10,000 students, consider using PCA over t-SNE for faster projections
- **Memory Usage**: Room allocation with >50,000 students may require increased memory allocation
- **Clustering Time**: Optuna optimization scales with trial count; 200 trials recommended for most use cases

##  Version History

- **v1.0.0**: Initial release with basic clustering and room allocation
- **v1.1.0**: Added advanced search, column visibility, and categorical visualization options
- **v1.2.0**: Integrated automated clustering with Optuna optimization
- **v1.3.0**: Enhanced room search and student discovery features

---

*Built with ❤️ for university administrators and student housing management*
