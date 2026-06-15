# Example use cases

## GIS Analyst for Cats for the Humane Treatment of Humans

**Project:** the study area is the village of Youngstown, New York in the Town of Porter, New York state. 

**Objective:** produce maps and routes for people to visit all the residences that own cats in Youngstown on foot and bike (unicycle only), in the most efficient way possible. Avoiding those houses with dogs and pet birds. Don't travel up or down steep slopes. 

Tasked to gather and assess data for a project to canvas a neighborhood in the most efficient way, convey the quality of the data found and used, document the data, prepare the data, document the methods used to prepare the data to meet the objective, conduct analysis, create and share work products. 

The analyst will generally follow  a data science workflow.

* A data science workflow is a structured, step-by-step roadmap used to turn raw data into actionable insights, automated models, or business solutions. 
* While approaches vary, the process is inherently iterative and generally follows these core stages:
1. Define the Problem: Understand the business goal or question. Establish what problem you are solving, success metrics, and what data might be needed.
2. Acquire Data: Collect raw data from various sources such as SQL databases, APIs, or files.
3. Inspect and Prepare Data: Raw data is typically messy. Data scientists clean and preprocess this data by handling missing values, fixing errors, and transforming it into a model-ready format.
4. Explore Data: Conduct Exploratory Data Analysis (EDA) to summarize main characteristics, spot anomalies, and uncover underlying patterns using visualizations and statistical tests.
5. Model Data: Build and train machine learning algorithms. This involves testing multiple models, tuning parameters, and validating their performance to find the best fit.
6. Evaluate Results: Assess the model using specific metrics (e.g., accuracy, precision) to ensure it performs well and addresses the original problem statement.
7. Deploy and Communicate: Put the model into production or translate findings into dashboards, reports, and storytelling for business stakeholders.
   
To ensure the reliability and efficiency of these tasks, modern data science workflows strongly emphasize clear documentation, code review, and version control (like using GitHub) to preserve institutional knowledge.

#### The analyst finds data:
1. Geospatial vector data from
 * the State of New York in File Geodatabase format in the SRS EPSG 4629: highways, rivers, historical places, building outlines and attributes including address
 * niagara county in shapefile format in some local SRS in feet units: property parcels, roads (non-routable yet)
 * federal sources as Geopackages in NAD83 lat longs: GNIS
2. Tabular data from
 * the organization Cats for the Humane Treatment of Humans, including a PostgresQL/PostGIS database: tabular spy cat home attributes, human home attributes, including addresses for each and list of occupants
3. raster data from
 * orthophotos from usgs in Geotiff format
 * lidar from usgs in LAS format

#### Steps
1. Documents the originals datasets and assesses for common data issues
2. Re-projects/warps data to a high-resolution, local SRS for Youngstown
3. Uses village bounds to clip all data to limit extents
4. geocodes all tabular addresses to create points
5. create a route-able street network from roads
6. select human homes associated with cat homes that meet the needed criteria
7. plan the routes that meet the objectives
8. create maps and textual plans based on the optimized routes. hand outs for each canvaser
9. create a fully documented data repository of the project for future projects or revising this one

