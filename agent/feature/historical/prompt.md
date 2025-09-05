## Objective
Separately from the future projections model, we are going to aggregate and plot historical yearly (fiscal and calendar) interest expense. Put all the code into 'src/historical.py'. Write tests as usual.

## Processing: Interest Expense sheet
- Source: the most recent file in 'input/' with the filename pattern 'IntExp_*'.
- Read in the file and then drop rows that do not have Expense Category Description 'INTEREST EXPENSE ON PUBLIC ISSUES'. e.g., the GAS related rows which are intra-government transfers.
- Extract 'Calendar Year', 'Fiscal Year', and 'Month' from 'Record Date'. The government fiscal year ends after September (starts in October).

## Processing: GDP
- We will also be using GDP data to display results as a percentage of GDP. 
- Source: 'input/GDP.xlsx'. Read in that file and drop rows older than year 2000.
- GDP is updated quarterly (e.g. on January 1, April 1, etc.). We need to expand the data to include every month. Fill the in-between months linearly. For example, if GDP on 1/1/2026 was 40000 and GDP on 4/1/2026 was 43000, we would fill GDP for 2/1/2026 and 3/1/2026 with 41000 and 42000 respectively.
- Join GDP data to Interest Expense data on month and year. Ensure that the dates line up and the join goes smoothly.

## Aggregation / Spreadsheet Output
- Write outputs to 'output/historical/spreadsheets/'
- Sum the 'Current Month Expense Amount' column and group by calendar year.
- Sum the 'Current Month Expense Amount' column and group by fiscal year.
- Sum the 'Current Month Expense Amount' column and group by calendar year and month.
- Sum the 'Current Month Expense Amount' column and group by fiscal year and month.
- Sum the 'Current Month Expense Amount' column and group by both calendar year and Expense Type Description.
- Sum the 'Current Month Expense Amount' column and group by both fiscal year and Expense Type Description.
- For each of these tables: Rename the aggregated 'Current Month Expense Amount' to 'Interest Expense'. Create two new columns 'Interest Expense (millions)' and 'Interest Expense (billions)'. Write each one to a separate .csv file.
- Create a new column with 'Interest Expense (% GDP)'. Note that the raw GDP data is already in billions of dollars, so we can use the 'Interest Expense (billions)' column.
- Combine all of these tables into a single .xlsx file in separate tabs.

## Chart Output
- Write .png to 'output/historical/visualizations/'
- Line chart with 'Interest Expense (billions)' on y-axis and year on x-axis. Plot calendar year and fiscal year versions on separate charts.
- Same chart as above using Interest Expense (% GDP).
- Stacked area chart versions of the above chart for the tables that are grouped by Expense Type Description.

## Other Output
- Save copies of the GDP and Interest Expense inputs into 'output/historical/source_data/' 