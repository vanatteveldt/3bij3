# 3bij3 - A framework for testing recommender systems and their effects 

## Installation

1. Clone the repository

```
git clone https://github.com/nickma101/3bij3
cd 3bij3
```

2. Create a virtual environment and activate it:

```
python3 -m venv venv
source venv/bin/activate
```

3. Install requirements with 

```
pip install -r requirements.txt
```

4. Set up an elasticsearch database with news articles (Infos on how to install this are [here](https://github.com/uvacw/inca/blob/development/doc/gettingstarted.md) under point 3)

```
docker run --name elastic -dp 9200:9200 -p 9300:9300 -e "discovery.type=single-node" -e 'ES_JAVA_OPTS=-Xms800m -Xmx800m'  docker.elastic.co/elasticsearch/elasticsearch:7.11.1
```

`#TODO: create a small script to insert example data`

(depending on you settings, you might need to run the first command as administrator, e.g. `sudo docker ...`)

5. Initialise the database with the following commands:

```python3
flask db init
flask db migrate
flask db upgrade
```

`#TODO: Create user`

## Usage

Run a local server with:

```
FLASK_APP=3bij3.py flask run
```

If you run into problems and/or for more advanced and detailed instructions see original version and instructions: https://github.com/FeLoe/3bij3
