import streamlit as st
import pickle
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import sqlite3

# Configuration
OMDB_API_KEY = "b66ea239"  # Replace with your OMDb API key
OMDB_BASE_URL = "http://www.omdbapi.com/?t={}&apikey={}"

# Set up requests session with retries
session = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
session.mount("http://", HTTPAdapter(max_retries=retries))


# Cache posters in SQLite
def init_cache():
    conn = sqlite3.connect("posters.db")
    cursor = conn.cursor()
    # Drop existing table to ensure correct schema
    cursor.execute("DROP TABLE IF EXISTS posters")
    cursor.execute("CREATE TABLE posters (title TEXT PRIMARY KEY, poster_url TEXT)")
    conn.commit()
    conn.close()


def get_cached_poster(title):
    conn = sqlite3.connect("posters.db")
    cursor = conn.cursor()
    cursor.execute("SELECT poster_url FROM posters WHERE title = ?", (title,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


def save_poster_url(title, poster_url):
    conn = sqlite3.connect("posters.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO posters (title, poster_url) VALUES (?, ?)", (title, poster_url))
    conn.commit()
    conn.close()


# Initialize cache
init_cache()

# Load movie data and similarity matrix
try:
    movies_dict = pickle.load(open('movie_dict.pkl', 'rb'))
    movies = pd.DataFrame(movies_dict)
    similarity = pickle.load(open('similarity.pkl', 'rb'))
except FileNotFoundError:
    st.error("Error: movie_dict.pkl or similarity.pkl not found in the project directory.")
    st.stop()


def fetch_movie_poster(title):
    """
    Fetch movie poster URL using movie title from OMDb API.
    Checks cache first, then makes API call with retries.
    Returns the poster URL or None if the request fails.
    """
    # Check cache
    cached_poster = get_cached_poster(title)
    if cached_poster:
        return cached_poster

    # Make OMDb API request
    url = OMDB_BASE_URL.format(title.replace(" ", "+"), OMDB_API_KEY)
    try:
        response = session.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("Response") == "True":
                poster_url = data.get("Poster")
                if poster_url and poster_url != "N/A":
                    save_poster_url(title, poster_url)
                    return poster_url
                else:
                    st.warning(f"No poster found for '{title}'")
                    return None
            else:
                st.warning(f"Movie '{title}' not found in OMDb")
                return None
        else:
            st.error(f"OMDb API request failed with status code {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        st.error(f"Network error for '{title}': {e}")
        return None
    finally:
        time.sleep(0.1)  # Respect OMDb rate limit (1,000 requests/day)


def recommend(movie):
    """
    Generate movie recommendations based on selected movie.
    Returns a list of recommended movie names and their poster URLs.
    """
    recommended_movies_name = []
    recommended_movies_poster = []

    try:
        movie_index = movies[movies['title'] == movie].index[0]
        distances = similarity[movie_index]
        movies_list = sorted(list(enumerate(distances)), reverse=True, key=lambda x: x[1])[1:6]

        for i in movies_list:
            movie_title = movies.iloc[i[0]].title.strip().title()  # Normalize title
            recommended_movies_name.append(movie_title)
            poster_url = fetch_movie_poster(movie_title)
            recommended_movies_poster.append(
                poster_url if poster_url else "https://via.placeholder.com/500x750?text=No+Poster")
    except IndexError:
        st.error("Selected movie not found in the database.")
        return [], []

    return recommended_movies_name, recommended_movies_poster


# Streamlit app
st.title('FilmFlux')

# Dropdown for movie selection
selected_movie_name = st.selectbox(
    'Type or select a movie to get recommendation',
    movies['title'].values
)

if st.button('Recommend'):
    if selected_movie_name:
        with st.spinner("Fetching recommendations and posters..."):
            recommended_movies_name, recommended_movies_poster = recommend(selected_movie_name)
        if recommended_movies_name:
            st.subheader("Recommended Movies")
            cols = st.columns(5, gap='large')
            for i, (name, poster) in enumerate(zip(recommended_movies_name, recommended_movies_poster)):
                with cols[i]:
                    st.image(poster, caption=name, width=150, use_container_width=False)
        else:
            st.warning("No recommendations found for the selected movie.")
    else:

        st.warning("Please select a movie.")
