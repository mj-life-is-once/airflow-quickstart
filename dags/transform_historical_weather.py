"""DAG that runs a transformation on data in DuckDB using the Astro SDK"""

# --------------- #
# PACKAGE IMPORTS #
# --------------- #

import pandas as pd
from airflow.datasets import Dataset
from airflow.decorators import dag, task

# import tools from the Astro SDK
from astro import sql as aql
from astro.sql.table import Table
from pendulum import datetime

from include.global_variables import airflow_conf_variables as gv
from include.global_variables import constants as c
from include.global_variables import user_input_variables as uv

# -------------------- #
# Local module imports #
# -------------------- #


# ----------------- #
# Astro SDK Queries #
# ----------------- #


# Create a reporting table that counts heat days per year for each city location
@aql.transform(pool="duckdb")
def create_historical_weather_reporting_table(in_table: Table, hot_day_celsius: float):
    return """
        SELECT time, city, temperature_2m_max AS day_max_temperature,
        SUM(
            CASE
            WHEN CAST(temperature_2m_max AS FLOAT) >= {{ hot_day_celsius }} THEN 1
            ELSE 0
            END
        ) OVER(PARTITION BY city, YEAR(CAST(time AS DATE))) AS heat_days_per_year
        FROM {{ in_table }}
    """


# --- #
# DAG #
# --- #

# ---------- #
# Exercise 1 #
# ---------- #
# Schedule this DAG to run as soon as the 'extract_historical_weather_data' DAG has finished running.
# Tip: You will need to use the dataset feature.
historical_dataset = Dataset("duckdb://include/dwh/historical_weather_data")


@dag(
    start_date=datetime(2023, 1, 1),
    # this DAG runs as soon as the climate and weather data is ready in DuckDB
    schedule=[historical_dataset],
    catchup=False,
    default_args=gv.default_args,
    description="Runs transformations on climate and current weather data in DuckDB.",
    tags=["part_2"],
)
def transform_historical_weather():

    create_historical_weather_reporting_table(
        in_table=Table(
            name=c.IN_HISTORICAL_WEATHER_TABLE_NAME, conn_id=gv.CONN_ID_DUCKDB
        ),
        hot_day_celsius=uv.HOT_DAY,
        output_table=Table(
            name=c.REPORT_HISTORICAL_WEATHER_TABLE_NAME, conn_id=gv.CONN_ID_DUCKDB
        ),
    )

    # ---------- #
    # Exercise 3 #
    # ---------- #
    # Use pandas to transform the 'historical_weather_reporting_table' into a table
    # showing the hottest day in your year of birth (or the closest year, if your year
    # of birth is not available for your city).
    # Tip: the saved dataframe will be shown in your streamlit App.

    @task(
        pool="duckdb",
    )
    def find_hottest_day_birthyear(
        duckdb_conn_id: str,
        input_table_name: pd.DataFrame,
        birthyear: int,
        output_table_name: str,
    ):

        from duckdb_provider.hooks.duckdb_hook import DuckDBHook

        duckdb_conn = DuckDBHook(duckdb_conn_id).get_conn()
        cursor = duckdb_conn.cursor()
        input_df = cursor.sql(
            f"""
            SELECT * FROM {input_table_name}
            """
        ).df()

        ####### YOUR TRANSFORMATION ##########
        input_df["time"] = pd.to_datetime(input_df["time"])
        output_df = input_df[input_df["time"].dt.year == birthyear]
        output_df = output_df[output_df["city"] == uv.MY_CITY]
        # filter the temperature greater than uv.HOT_DAY
        # output_df = output_df[output_df["temperature_2m_max"] > uv.HOT_DAY]

        # remove lat, log
        output_df = output_df.drop(columns=["lat", "long"])
        # rename columns
        output_df = output_df.rename(
            columns={
                "time": "Time",
                "temperature_2m_max": "Max Temperature",
                "city": "City",
            }
        )
        # change datetime format
        output_df["Time"] = output_df["Time"].dt.strftime("%Y-%m-%d")
        # output_df["Max Temperature"] = output_df["Max Temperature"].astype(float)
        # filter the temperature greater than uv.HOT_DAY
        # output_df = output_df[output_df["Max Temperature"] > uv.HOT_DAY]
        # drop previous table
        cursor.sql(f"DROP TABLE IF EXISTS {output_table_name}")
        # saving the output_df to a new table
        cursor.sql(
            f"CREATE TABLE IF NOT EXISTS {output_table_name} AS SELECT * FROM output_df"
        )
        cursor.sql(f"INSERT INTO {output_table_name} SELECT * FROM output_df")
        cursor.close()

    find_hottest_day_birthyear(
        duckdb_conn_id=gv.CONN_ID_DUCKDB,
        input_table_name=c.IN_HISTORICAL_WEATHER_TABLE_NAME,
        birthyear=uv.BIRTH_YEAR,
        output_table_name=c.REPORT_HOT_DAYS_TABLE_NAME,
    )


transform_historical_weather()
