import  numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from src.cfg import CFG
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import holidays


class Feategg:
    def __init__(self, df: pd.DataFrame):
        self.df = self.feature_eng(df)
        self.df = self._add_gdp(self.df)
        self.train_df = self.df[self.df['test'] == 0]
        self.test_df = self.df[self.df['test'] == 1]
        
        self.df, self.fig_sinu_sell = self._add_signFeatures(self.df)
        
        self.df = self._add_holidays(self.df)
        
        self.df, self.year_ratio = self._get_year_ratio(self.df)
        
    def _get_year_ratio(self, df: pd.DataFrame):
        abt_holidays = df.copy()
        abt = df.copy()
        abt_holidays['holiday_response'] = 0
        for country in CFG.countries:
            for holiday, _ in holidays.CountryHoliday(CFG.countries_21[country], years=CFG.years).items():
                abt_holidays.loc[(abt_holidays['country'] == country) & abt_holidays['date'].isin(pd.date_range(holiday, periods=CFG.holiday_response_len)), 'holiday_response'] = 1
                
        data = pd.DataFrame()

        for n, country in enumerate(CFG.countries):
            dt = abt_holidays[(abt_holidays['country'] == country) & (abt_holidays['test'] == 0)].groupby('dayofyear')['total'].median()
            data[country] = dt
            
        data['median'] = data.median(axis=1)

        # linear regressio on forier series
        x = data.index.to_numpy()
        y = data['median'].to_numpy()
        fourier = lambda t: np.array([np.sin(2 * np.pi/365 * t), np.cos(2 * np.pi/365 * t)])

        year_ratio = Ridge(alpha=0.1).fit(fourier(x).T, y.T).predict(fourier(np.arange(1, 366)).T)
        year_ratio = np.append(year_ratio, year_ratio[-1])

        abt['dayofyear_factor'] = abt['dayofyear'].map(dict(zip(range(1, 367), year_ratio)))

        abt['ratio'] = abt['gdp_factor'] * abt['product_factor'] * abt['store_factor'] * abt['weekday_factor'] * abt['dayofyear_factor']
        abt['total'] = abt['num_sold'] / abt['ratio']

        # plt.plot(year_ratio, 'k', label='median')
        return abt, year_ratio

    def _add_holidays(self, df: pd.DataFrame):
        abt = df.copy()
        abt['holiday'] = 0
        for country in CFG.countries:
            days = [str(day) for day in holidays.CountryHoliday(CFG.countries_21[country], years=CFG.years).items()]
            abt.loc[(abt['country'] == country) & (abt['date'].dt.date.astype(str).isin(days)), 'holiday'] = 1


        num_sold_per_week_country_week_day = abt.groupby(['weeknum', 'country', 'weekday'])['num_sold'].sum().reset_index().pivot(index=['weeknum', 'country'], columns='weekday')

        ratio_sold_per_week_country_weekday = num_sold_per_week_country_week_day.apply(lambda row: row/sum(row),axis=1).reset_index()

        ratio_weekday = pd.DataFrame(columns=CFG.countries, data=[[0, ]*len(CFG.countries)]*7)
        for n, country in enumerate(CFG.countries):
            for d in range(7):
                dt = ratio_sold_per_week_country_weekday.loc[ratio_sold_per_week_country_weekday.country == country, ('num_sold', d)][:-60]
                ratio_weekday.loc[d, country] = dt.median()
                
        ratio_weekday_mean = ratio_weekday.mean(axis=1)
        ratio_weekday['mean'] = ratio_weekday_mean

        abt['weekday_factor'] = abt.weekday.map(ratio_weekday_mean)

        abt['ratio'] = abt['gdp_factor'] * abt['product_factor'] * abt['store_factor'] * abt['weekday_factor']
        abt['total'] = abt['num_sold'] * abt['ratio']
        return abt
    
    def _add_signFeatures(self, df: pd.DataFrame):
        abt = df.copy()
        abt_no_ken_can = abt[~abt.country.isin(['Kenya', 'Canada'])].copy()
        total = abt_no_ken_can.groupby(by='date').num_sold.sum().rename('num_sold_total')
        abt_no_ken_can = abt_no_ken_can.join(total, on='date', how='left')
        abt_no_ken_can['num_sold_ratio'] = abt_no_ken_can['num_sold'] / abt_no_ken_can['num_sold_total']

        fig = make_subplots(rows=len(CFG.products), cols=1, 
                       subplot_titles=[f"Product: {product}" for product in CFG.products],
                       vertical_spacing=0.05)
        abt['product_factor'] = None
        for idx, product in enumerate(CFG.products, 1):
            abt_no_ken_can_date = abt_no_ken_can[
                (abt_no_ken_can['product'] == product) & 
                (abt_no_ken_can.test == 0)
            ].groupby('date')
            
            x = abt_no_ken_can_date[CFG.sincoscol].mean().to_numpy()
            y = abt_no_ken_can_date.num_sold_ratio.sum().to_numpy()
            
            reg = Ridge(alpha=0.1).fit(x, y)
            p = reg.predict(x)
            
            abt.loc[(abt['product'] == product), 'product_factor'] = reg.predict(
                abt.loc[(abt['product'] == product), CFG.sincoscol].to_numpy()
            )
            
            fig.add_trace(
                go.Scatter(
                    y=y,
                    mode='lines',
                    name=f'{product} - Actual',
                    line=dict(color='blue'),
                    # legend='legend1'
                ),
                row=idx, col=1
            )
            
            fig.add_trace(
                go.Scatter(
                    y=p,
                    mode='lines',
                    name=f'{product} - Predicted',
                    line=dict(color='red'),
                    # legend='legend2'
                ),
                row=idx, col=1
            )
        
        # Update layout
        fig.update_layout(
            height=300 * len(CFG.products),
            width=800,
            showlegend=True,
            title_text="Product Sales Ratio Analysis",
        )
        
        return abt, fig

    def feature_eng(self, df: pd.DataFrame):
        # abt = pd.concat([train_df, test_df])
        abt = df.copy()
        abt['year'] = abt.date.dt.year
        abt['month'] = abt.date.dt.month
        abt['weekday'] = abt.date.dt.weekday
        abt['dayofyear'] = abt.date.dt.dayofyear
        abt['daynum'] = (abt.date - abt.date.iloc[0]).dt.days
        abt['weeknum'] = abt.daynum // 7


        dayisinyear = (abt.groupby('year').id.count() / len(CFG.countries) / len(CFG.stores) / len(CFG.products)).rename('dayisinyear').astype(int).to_frame()
        abt = abt.merge(dayisinyear, on='year', how='left')
        abt['partofyear'] = (abt['dayofyear'] - 1) / abt['dayisinyear'] # sinusoidal
        abt['partof2year'] = abt['dayofyear'] + abt['year'] % 2 # sinusoidal
        abt['sin 4t'] = np.sin(8 * np.pi * abt['partofyear'])  
        abt['cos 4t'] = np.cos(8 * np.pi * abt['partofyear'])
        abt['sin 3t'] = np.sin(6 * np.pi * abt['partofyear'])
        abt['cos 3t'] = np.cos(6 * np.pi * abt['partofyear'])
        abt['sin 2t'] = np.sin(4 * np.pi * abt['partofyear'])
        abt['cos 2t'] = np.cos(4 * np.pi * abt['partofyear'])
        abt['sin t'] = np.sin(2 * np.pi * abt['partofyear'])
        abt['cos t'] = np.cos(2 * np.pi * abt['partofyear']) # partofyear takes half a year to complete
        abt['sin t/2'] = np.sin(np.pi * abt['partof2year']) # partof2year takes a year to complete
        abt['cos t/2'] = np.cos(np.pi * abt['partof2year'])
        abt.drop(['partofyear', 'partof2year', 'dayisinyear'], axis=1, inplace=True)

        abt = self._add_gdp(abt)

        abt_no_ken_can = abt[~abt.country.isin(['Kenya', 'Canada'])] # keya and canada contains NaN values
        store_df = abt_no_ken_can.groupby(by='store').num_sold.mean().rename('store_factor').to_frame()
        abt = abt.drop('store_factor', axis=1, errors='ignore').join(store_df, on='store', how='left')

        return abt

    def _add_gdp(self, df):
        abt = df.copy()
        gdp_df = pd.read_csv("data/gdp_per_capita.csv")
        gdp_df.index = CFG.countries
        gdp_df.columns = CFG.years

        abt['gdp_factor'] = None
        for year in CFG.years:
            for country in CFG.countries:
                abt.loc[(abt.year == year) & (abt.country == country), 'gdp_factor'] = gdp_df.loc[country, year]
        
        return abt