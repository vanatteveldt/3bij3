from flask import render_template, flash, redirect, url_for, request, make_response, session, Markup
from app import app, db, mail, recommender
from flask_login import current_user, login_user, logout_user, login_required
from app.models import User, News, News_sel, Category, Points_logins, Points_stories, Points_invites, Points_ratings, User_invite, Num_recommended, Show_again, Diversity
from werkzeug.urls import url_parse
from app.forms import RegistrationForm, ChecklisteForm, LoginForm, ReportForm,  ResetPasswordRequestForm, ResetPasswordForm, rating, ContactForm
import string
import random
import re
from app.email import send_password_reset_email, send_registration_confirmation
from datetime import datetime
from app.recommender import recommender
from sqlalchemy import desc
from flask_mail import Message
from user_agents import parse
from app.processing import paragraph_processing
from werkzeug.security import generate_password_hash
from app.vars import host, indexName, es, list_of_sources, topics, doctype_dict, topic_list
from app.vars import num_less, num_more, num_select, num_recommender
from app.vars import topicfield, textfield, teaserfield, teaseralt, titlefield, doctypefield, classifier_dict
from app.vars import group_number
from app.vars import p1_day_min, p1_points_min, p2_day_min, p2_points_min
import webbrowser

rec = recommender()
paragraph = paragraph_processing()

@app.route('/login', methods = ['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('count_logins'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username = form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Ongeldige gebruikersnaam of wachtwoord')
            return redirect(url_for('login'))
        login_user(user, remember=form.remember_me.data)
        try:
            user.panel_id(panel_id)
        except:
            pass
        user_guest = user.username
        user_invite_guest = User_invite.query.filter_by(user_guest = user_guest).first()
        if user_invite_guest is not None:
            user_invite_guest.times_logged_in = user_invite_guest.times_logged_in + 1
            db.session.commit()
        return redirect(url_for('count_logins'))
    return render_template('login.html', title='Inloggen', form=form)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('count_logins'))

@app.route('/consent', methods = ['GET', 'POST'])
def consent():
    parameter = request.args.to_dict()
    try:
        other_user = parameter['user']
    except:
        other_user = None
    if other_user is not None:
        other_user = other_user
    else:
        other_user = None
    try:
        panel_id = parameter['pid']
    except:
        try:
            panel_id = parameter['PID']
        except:
            panel_id = "noIDyet"
    return render_template('consent.html', other_user = other_user, panel_id = panel_id)

@app.route('/no_consent')
def no_consent():
    return render_template('no_consent.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('count_logins'))
    parameter = request.args.to_dict()
    try: 
        panel_id = parameter['id']
    except:
        panel_id = "noIDyet"
    form = RegistrationForm()
    if form.validate_on_submit():
        group_list = list(range(1, group_number + 1))
        group = random.choices(population = group_list, weights = [0.2, 0.3, 0.3, 0.2], k = 1)
        user = User(username=form.username.data, group = group, panel_id = panel_id, email_contact = form.email.data)
        user.set_password(form.password.data)
        user.set_email(form.email.data)
        db.session.add(user)
        db.session.commit()
        try:
            other_user = request.args.to_dict()['other_user']
        except:
            other_user = None
        if other_user is not None:
            other_user = other_user
            user_invite = User_invite(stories_read = 0, times_logged_in = 0, user_host = other_user, user_guest = form.username.data)
            db.session.add(user_invite)
            db.session.commit()
        send_registration_confirmation(user, form.email.data)    
        flash('Gefeliciteerd, je bent nu een ingeschreven gebruiker!')
        return redirect(url_for('login', panel_id = panel_id))
    return render_template('register.html', title = 'Registratie', form=form)



@app.route('/activate', methods=['GET', 'POST'])
def activate():
    parameter = request.args.to_dict()
    try:
        user = parameter['user']
    except:
        user = "no_user"
    check_user = User.query.filter_by(id = user).first()
    if check_user is not None:
        if check_user.activated == 0:
            check_user.activated = 1
            db.session.commit()
            redirect_link = "".format(check_user.panel_id)
            flash('Gefeliciteerd, je account is nu geactiveerd!')
            try:
                return webbrower.open_new_tab(redirect_link)
            except:
                return redirect(redirect_link)
        elif check_user.activated == 1:
            flash('Je account is al geactiveerd, veel plezier op de website!')
            return redirect(url_for('login'))
    else:
        flash('Er ging iets mis. Heb je al een account aangemaakt op de website?')
        return redirect(url_for('login'))
            
        

@app.route('/', methods = ['GET', 'POST'])
@app.route('/homepage', methods = ['GET', 'POST'])
@login_required
def newspage(show_again = 'False'):
    number_rec = Num_recommended(num_recommended = num_recommender, user_id = current_user.id)
    results = []
    parameter = request.args.to_dict()
    try:
        show_again = parameter['show_again']
    except KeyError:
        show_again = "False"
    if show_again == 'True':
        documents = last_seen()
        decision = Show_again(show_again = 1, user_id = current_user.id)
        db.session.add(decision)
    elif show_again == 'False':
        documents = which_recommender()
        decision = Show_again(show_again = 0, user_id = current_user.id)
        db.session.add(decision)
        if documents == "not enough stories":
            return render_template('no_stories_error.html')
    for idx, result in enumerate(documents):
        news_displayed = News(elasticsearch = result["_id"], url = result["_source"]["url"], user_id = current_user.id, recommended = result['recommended'], position = idx)
        db.session.add(news_displayed)
        db.session.commit()
        result["new_id"] = news_displayed.id
        text_clean = re.sub(r'\|','', result["_source"][titlefield])
        if text_clean.startswith(('artikel ', 'live ')):
            text_clean = text_clean.split(' ', 1)[1]
        elif re.match('[A-Z]*? - ', text_clean):
            text_clean = re.sub('[A-Z]*? - ', '', text_clean)
        try:
            teaser = result["_source"][teaserfield]
        except KeyError:
            teaser = result["_source"][textfield]
        teaser = re.sub('[A-Z]*? - ', '', teaser)
        result["_source"]["teaser"] = teaser
        result["_source"]["text_clean"] = text_clean
        if topics == True:
            if topicfield in result['_source'].keys():
                result["_source"]["topic_string"] = result['_source'][topicfield]
                if result["_source"]["topic_string"] == "Justitie":
                    result["_source"]["topic_string"] = "Crime" 
                results.append(result)
            else:
                pass
        else:
            pass
    session['start_time'] = datetime.utcnow()

    user_guest = current_user.username
    user_invite_guest = User_invite.query.filter_by(user_guest = user_guest).first()
    if user_invite_guest is not None:
        user_invite_guest.stories_read = user_invite_guest.stories_read + 1
        db.session.commit()
    different_days = days_logged_in()['different_dates']
    points = points_overview()['points']
    group = current_user.group
    href_final = "https://vuamsterdam.eu.qualtrics.com/jfe/form/SV_38UP20nB0r7wv3f?id={}&group={}&fake={}".format(current_user.panel_id, current_user.group, current_user.fake)
    message_final = 'Je kunt deze studie nu afsluiten en een finale vragenlijst invullen - klik <a href={} class="alert-link">hier</a> - maar je kunt de webapp ook nog wel verder gebruiken.'.format(href_final)
    href_first = "https://vuamsterdam.eu.qualtrics.com/jfe/form/SV_b7XIK4EZPElGJN3?id={}&group={}".format(current_user.panel_id, current_user.group)
    message_first = 'Je kunt nu de eerste deel van deze studie afsluiten door een aantal vragen te beantwoorden. Klik <a href={} class="alert-link">hier</a> om naar de vragenlijst te gaan. aan het einde van de vragenlijst vindt je een link die je terugbrengt naar de website voor het tweede deel. Om de studie succesvol af te ronden, moet je aan beide delen deelnemen.'.format(href_first)
    message_final_b = 'Je kunt deze studie nu afsluiten en een finale vragenlijst invullen - klik <a href={} class="alert-link">hier</a> - maar je kunt de webapp ook nog wel verder gebruiken.'.format(href_first)
    
    if different_days >= p2_day_min and points >= p2_points_min and (group == 1 or group == 2 or group == 3) and current_user.phase_completed == 2:
        flash(Markup(message_final))
    elif current_user.phase_completed == 2 and (group == 2 or group == 3):
        flash(Markup('Er zijn nu nieuwe functies om 3bij3 naar jouw wensen te personaliseren. Klik <a href="/points" class="alert-link">hier</a> of ga naar "Mijn 3bij3" en probeer ze uit!'))
    elif p1_day_min <= different_days and p1_points_min <= points and current_user.phase_completed == 1 and (group == 1 or group == 2 or group == 3):
        flash(Markup(message_first))
    elif different_days >= p1_day_min and points >= p1_points_min and group == 4 and current_user.phase_completed == 1:
        flash(Markup(message_final_b))
    elif current_user.phase_completed == 3:
        flash(Markup('Bedankt voor het afronden van de studie. Je kunt nog steeds 3bij3 blijven gebruiken als je dat wilt.')) 
    return render_template('newspage.html', results = results)

def which_recommender():
	group = current_user.group
	method = rec.random_selection()
	return(method)
    
#    group = current_user.group
 #   if group == 1:
  #      method = rec.random_selection()
   # elif group == 2:
    #    selected_news = number_read()['selected_news']
     #   if selected_news < 3:
      #      method = rec.random_selection()
       # else:
        #    method = rec.past_behavior()
#    elif group == 3:
 #       selected_news = number_read()['selected_news']
  #      if selected_news == 0:
   #         method = rec.random_selection()
    #    else:
     #       method = rec.past_behavior_topic()
#    elif group == 4:
 #       categories = Category.query.filter_by(user_id = current_user.id).order_by(desc(Category.id)).first()
  #      if categories == None:
   #         method  = rec.random_selection()
    #    else:
     #       method = rec.category_selection_classifier()
#    return(method)


def last_seen():
    news = News.query.filter_by(user_id = current_user.id).order_by(desc(News.id)).limit(9)
    news_ids = [item.elasticsearch for item in news]
    recommended = [item.recommended for item in news]
    id_rec = zip(news_ids, recommended)
    news_last_seen = []
    for item in id_rec:
        doc = es.search(index=indexName,
                  body={"query":{"term":{"_id":item[0]}}}).get('hits',{}).get('hits',[""])
        for text in doc:
                text['recommended'] = item[1]
                news_last_seen.append(text)
    return news_last_seen

@app.route('/logincount', methods = ['GET', 'POST'])
@login_required
def count_logins():
    parameter = request.args.to_dict()
    try:
        show_again = parameter['show_again']
    except KeyError:
        show_again = "False"
    try:
        user_string = request.headers.get('User-Agent')
        user_string = str(parse(user_string))
    except:
        user_string = " "
    points_logins = Points_logins.query.filter_by(user_id = current_user.id).all()
    if points_logins is None or points_logins == []:
        logins = Points_logins(points_logins = 2, user_id = current_user.id)
        db.session.add(logins)
    else:
        dates = [item.timestamp.date() for item in points_logins]
        now = datetime.utcnow()
        points_today = 0
        for date in dates:
            if date == now.date():
                points_today += 2
            else:
                pass
        try:
            date = current_user.last_visit
            if date is None:
                date = current_user.first_login
        except:
            date = datetime.utcnow()
        difference = now - date
        difference = int(difference.seconds // (60 * 60))
        if difference > 1:
            if points_today >= 4:
                logins = Points_logins(points_logins = 0, user_id = current_user.id, user_agent = user_string)
                db.session.add(logins)
            else:
                logins = Points_logins(points_logins = 2, user_id = current_user.id, user_agent = user_string)
                db.session.add(logins)
        else:
            pass
        current_user.last_visit = datetime.utcnow()
    db.session.commit()
    return redirect(url_for('newspage', show_again = show_again))

@app.route('/save/<id>', methods = ['GET', 'POST'])
@login_required
def save_selected(id):
    selected = News.query.filter_by(id = id).first()
    es_id = selected.elasticsearch
    news_selected = News_sel(news_id = selected.elasticsearch, user_id =current_user.id, )
    db.session.add(news_selected)
    db.session.commit()
    selected_id = News_sel.query.filter_by(user_id = current_user.id).order_by(desc(News_sel.id)).first().__dict__['id']
    points_stories = Points_stories.query.filter_by(user_id = current_user.id).all()
    if points_stories is None:
        stories = Points_stories(points_stories = 1, user_id = current_user.id)
        db.session.add(stories)
    else:
        dates = [item.timestamp.date() for item in points_stories]
        now = datetime.utcnow().date()
        points_today = 0
        for date in dates:
            if date == now:
                points_today += 1
            else:
                pass
        if points_today >= 10:
            stories = Points_stories(points_stories = 0, user_id = current_user.id)
            db.session.add(stories)
        else:
            stories = Points_stories(points_stories = 1, user_id = current_user.id)
            db.session.add(stories)
    db.session.commit()
    return redirect(url_for('show_detail', id = selected_id))

@app.route('/detail/<id>', methods = ['GET', 'POST'])
@login_required
def show_detail(id):
     selected = News_sel.query.filter_by(id = id).first()
     es_id = selected.news_id
     doc = es.search(index=indexName,
                  body={"query":{"term":{"_id":es_id}}}).get('hits',{}).get('hits',[""])
     for item in doc:
         text = item['_source'][rec.textfield]
         if "||" in text:
             text = re.split(r'\|\|\.\|\|', text)
             text = ''.join(text)
             text = re.split(r'\|\|\|', text)
             text = ''.join(text)
             text = re.split(r'\|\|', text)
         else:
             text = [text]
         text = paragraph.join_text(text)
         try:
             teaser = item['_source'][teaserfield]
         except KeyError:
            teaser = item['_source'][textfield][:50]
            teaser = re.sub(r'<.*?>',' ', teaser)
         title = item['_source']['title']
         url = item['_source']['url']
         publication_date = item['_source']['date']
         publication_date = datetime.strptime(publication_date, '%Y-%m-%dT%H:%M:%S')
         try:
             for image in item['_source']['images']:
                 image_url = image['url']
         except KeyError:
             image_url = []
             image_caption = []
         try:
             source = item['_source']['publisher']
         except KeyError:
             source = "onbekende bron"
     form = rating()
     if request.method == 'POST' and form.validate():
         selected.starttime = session.pop('start_time', None)
         selected.endtime =  datetime.utcnow()
         try:
             selected.time_spent = selected.endtime - selected.starttime
         except:
             selected.time_spent = None
         if request.form['rating'] == '':
             pass
         else:
             selected.rating = request.form['rating']
         if request.form['rating2'] == '':
             pass
         else:
             selected.rating2 = request.form['rating2']
         db.session.commit()
         points_ratings = Points_ratings.query.filter_by(user_id = current_user.id).all()
         if points_ratings is None:
             ratings = Points_ratings(points_ratings = 0.5, user_id = current_user.id)
             db.session.add(ratings)
         else:
             dates = [item.timestamp.date() for item in points_ratings]
             points = [item.points_ratings for item in points_ratings]
             points_dict = dict(zip(dates, points))
             now = datetime.utcnow().date()
             points_today = 0
             for key, value in points_dict.items():
                 if key == now:
                     points_today += value
                 else:
                     pass
             if points_today >= 5:
                 ratings = Points_ratings(points_ratings = 0, user_id = current_user.id)
                 db.session.add(ratings)
             else:
                 ratings = Points_ratings(points_ratings = 0.5, user_id = current_user.id)
                 db.session.add(ratings)
         db.session.commit()
         return redirect(url_for('decision'))

     session['start_time'] = datetime.utcnow()

     return render_template('detail.html', text = text, teaser = teaser, title = title, url = url, image = image_url, time = publication_date, source = source, form = form, id = id)


@app.route('/decision', methods = ['GET', 'POST'])
@login_required
def decision():
    return render_template('decision.html')


@app.route('/reset_password_request', methods= ['GET', 'POST'])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('count_logins'))
    form = ResetPasswordRequestForm()
    if form.validate_on_submit():
        email = form.email.data
        user = User.query.filter_by(email_contact = email).first()
        if user:
            send_password_reset_email(user, email)
        flash('Controleer uw email, u hebt informatie ontvangen hoe u uw wachtwoord opnieuw kunt instellen.')
        return redirect(url_for('login'))
    return render_template('reset_password_request.html', title="Wachtwoord opnieuw instellen", form=form)

@app.route('/reset_password/<token>', methods = ['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('count_logins'))
    user = User.verify_reset_password_token(token)
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash('Uw wachtwoord is opnieuw ingesteld worden.')
        return redirect(url_for('login'))
    return render_template('reset_password.html', form=form)


@app.context_processor
def time_logged_in():
    if current_user.is_authenticated:
        try:
            first_login = current_user.first_login
            difference_raw = datetime.utcnow() - first_login
            difference = difference_raw.days
        except:
            difference = 0
    else:
        difference = 0
    return dict(difference = difference)

@app.context_processor
def days_logged_in():
    if current_user.is_authenticated:
        points_logins = Points_logins.query.filter_by(user_id = current_user.id).all()
        if points_logins is None:
            different_dates = 0
        else:
            dates = [item.timestamp.date() for item in points_logins]
            different_dates = len(list(set(dates)))
    else:
        different_dates = 0
    return dict(different_dates = different_dates)

@app.context_processor
def number_read():
    if current_user.is_authenticated:
        try:
            selected_news = News_sel.query.filter_by(user_id = current_user.id).all()
            selected_news = len(selected_news)
        except:
            selected_news = 0
    else:
        selected_news = 0
    return dict(selected_news = selected_news)

@app.context_processor
def points_overview():
    if current_user.is_authenticated:
        user = User.query.filter_by(id = current_user.id).first()
        group = current_user.group
        phase_completed = current_user.phase_completed
        try:
            points_logins = user.sum_logins
            if points_logins is None:
                points_logins = 0
        except:
            points_logins = 0
        try:
            points_stories = user.sum_stories
            if points_stories is None:
                points_stories = 0
        except:
            points_stories = 0
        try:
            points_ratings = float(user.sum_ratings)
            if points_ratings is None:
                points_ratings = 0
        except:
            points_ratings = 0
        user_host = current_user.id
        user_invite_host = User_invite.query.filter_by(user_host = user_host).all()
        if user_invite_host is None:
            points_invites = 0
        else:
            number_invited = []
            for item in user_invite_host:
                item1 = item.__dict__
                if item1["stories_read"] >= 5 and item1["times_logged_in"] >= 2:
                    number_invited.append(item1['id'])
                    invites_points = Points_invites.query.filter_by(user_guest_new = item1['user_guest']).first()
                    if invites_points is None:
                         points_invites = Points_invites(user_guest_new = item1['user_guest'], points_invites = 5, user_id = current_user.id)
                         db.session.add(points_invites)
                         db.session.commit()
                    else:
                        points_invites = 0
                else:
                    points_invites = 0
        try:
            points_invites = user.sum_invites
            if points_invites is None:
                points_invites = 0
        except:
            points_invites = 0
        points = points_stories + points_invites + points_ratings + points_logins
        if group == 4:
            points_min = p1_points_min
        else:
            points_min = p2_points_min
        rest = points_min - (points_logins + points_stories + points_ratings)
        if rest <= 0:
            rest = 0
    else:
        points_stories = 0
        points_invites = 0
        points_ratings = 0
        points_logins = 0
        points = 0
        group = 1
        phase_completed = 0
        rest = 0
    
    return dict(points = points, points_ratings = points_ratings, points_stories = points_stories, points_invites = points_invites, points_logins = points_logins, group = group, phase = phase_completed, rest = rest)

@app.context_processor
def user_agent():
    user_string = request.headers.get('User-Agent')
    try:
        user_agent = parse(user_string)
        if user_agent.is_mobile == True:
            device = "mobile"
        elif user_agent.is_tablet == True:
            device = "tablet"
        else:
            device = "pc"
    except:
        user_agent = " "
        device = "pc"
    return dict(device = device)


@app.route('/decision/popup_back')
@login_required
def popup_back():
    return render_template('information_goback.html')


@app.route('/homepage/categories', methods = ['POST'])
@login_required
def get_categories():
    sel_categories = request.form.getlist('category')
    categories = []
    for category in topic_list:
        if category in sel_categories:
            categories.append(1)
        else:
            categories.append(0)
    category = Category(topic1 = categories[0], topic2 = categories[1], topic3 = categories[2], topic4 = categories[3], topic5= categories[4], \
topic6 = categories[5], topic7 = categories[6], topic8 = categories[7], topic9 = categories[8], topic10 = categories[9],  user_id = current_user.id)
    db.session.add(category)
    db.session.commit()
    return redirect(url_for('count_logins'))

@app.route('/contact', methods = ['GET', 'POST'])
@login_required
def contact():
    form = ContactForm()
    if request.method == 'POST':
        if form.validate() == False:
            return 'Vul alstublieft alle velden in <p><a href="/contact">Probeer het opnieuw!!! </a></p>'
        else:
            name =  current_user.username
            id = str(current_user.id)
            email =  form.email.data
            if not email or email == []:
                email = 'no_address_given'
            msg = Message("Message from your visitor " + name + "with ID: " + id,
                          sender= email,
                          recipients= ['felicia.loecherbach@gmail.com'])
            msg.body = """
            From: %s <%s>,
            %s
            %s
            """ % (name, email, form.lead.data, form.message.data)
            mail.send(msg)
            return redirect(url_for('count_logins'))
    elif request.method == 'GET':
        return render_template('contact.html', form=form)

@app.route('/faq', methods = ['GET'])
def faq():
    return render_template("faq.html")

@app.route('/points', methods = ['GET'])
@login_required
def get_points():
    points_stories_all = [item[0] for item in User.query.with_entities(User.sum_stories).all()]
    points_invites_all = [item[0] for item in User.query.with_entities(User.sum_invites).all()]
    points_ratings_all = [item[0] for item in User.query.with_entities(User.sum_ratings).all()]
    points_logins_all = [item[0] for item in  User.query.with_entities(User.sum_logins).all()]
    points_list = [points_stories_all, points_invites_all, points_ratings_all, points_logins_all]
    if points_stories_all is None:
        points_stories_all = [0]
    else:
        points_stories_all = [0 if x==None else x for x in points_stories_all]
    max_stories = max(points_stories_all)
    min_stories = min(points_stories_all)
    avg_stories  = round((sum(points_stories_all)/len(points_stories_all)),1)
    if points_invites_all is None:
        points_invites_all = [0]
    else:
        points_invites_all = [0 if x==None else x for x in points_invites_all]
    max_invites = max(points_invites_all)
    min_invites = min(points_invites_all)
    avg_invites  = round((sum(points_invites_all)/len(points_invites_all)), 1)
    if points_ratings_all is None:
        points_ratings_all = [0]
    else:
        points_ratings_all = [0 if x==None else x for x in points_ratings_all]
    points_ratings_all = [float(i) for i in points_ratings_all]
    max_ratings = max(points_ratings_all)
    min_ratings = min(points_ratings_all)
    avg_ratings  = round((sum(points_ratings_all)/len(points_ratings_all)), 1)
    if points_logins_all is None:
        points_logins_all = [0]
    else:
        points_logins_all = [0 if x==None else x for x in points_logins_all]
    max_logins = max(points_logins_all)
    min_logins = min(points_logins_all)
    avg_logins  = round((sum(points_logins_all)/len(points_logins_all)),1)

    points_overall = [sum(item) for item in zip(points_stories_all, points_logins_all, points_ratings_all, points_invites_all)]
    max_overall = max(points_overall)
    min_overall = min(points_overall)
    avg_overall  = round((sum(points_overall)/len(points_overall)), 2)
    group = current_user.group
    different_days = days_logged_in()['different_dates']
    points = points_overview()['points']
    rest = points_overview()['rest']
    phase = current_user.phase_completed
    if group == 4:
        points_min = p1_points_min
    else:
        points_min = p2_points_min
    try:
        num_recommended = Num_recommended.query.filter_by(user_id = current_user.id).order_by(desc(Num_recommended.id)).first().real
    except:
        num_recommended = 6
    try:
        diversity = Diversity.query.filter_by(user_id = current_user.id).order_by(desc(Diversity.id)).first().real
    except:
        diversity = 1
    return render_template("display_points.html",points_min = points_min,  max_stories = max_stories, min_stories = min_stories, avg_stories = avg_stories, max_logins = max_logins, min_logins = min_logins, avg_logins = avg_logins, max_ratings = max_ratings, min_ratings = min_ratings, avg_ratings = avg_ratings, max_invites = max_invites, min_invites = min_invites, avg_invites = avg_invites, points_overall = points_overall, max_overall = max_overall, min_overall = min_overall, avg_overall = avg_overall, phase = phase, num_recommended = num_recommended, diversity = diversity, rest = rest)


@app.route('/invite', methods = ['GET', 'POST'])
@login_required
def invite():
    id = current_user.id
    url = "https://www.3bij3.nl/consent?user={}".format(current_user.id)
    return render_template("invite.html", url = url, id = id)

@app.route('/report_article', methods = ['GET', 'POST'])
@login_required
def report_article():
    form = ReportForm()
    if request.method == 'POST':
        if form.validate() == False:
            return 'Vul alstublieft alle velden in <p><a href="/contact">Probeer het opnieuw!!! </a></p>'
        else:
            mail.send(msg)
            return redirect(url_for('count_logins'))
    elif request.method == 'GET':
        url = request.args.to_dict()['article']
        form.lead.data = "Probleem met artikel " + url
        return render_template('report_article.html', form=form, url = url)


@app.route('/phase_completed', methods = ['GET', 'POST'])
@login_required
def completed_phase():
    parameter = request.args.to_dict()
    try:
        wave_completed =int(parameter['phase_completed'])
        user_id = parameter['id']
        try: 
            fake = int(parameter['fake'])
        except:
            fake = 0
        if str(user_id) == current_user.panel_id and wave_completed == 2:
            user = User.query.filter_by(id = current_user.id).first()
            user.phase_completed = wave_completed
            user.fake = fake
            db.session.commit()
        elif str(user_id) == current_user.panel_id and wave_completed == 3:
            user = User.query.filter_by(id = current_user.id).first()
            user.phase_completed = wave_completed
            db.session.commit()
    except:
        pass
    return redirect(url_for('count_logins'))

@app.route('/diversity', methods = ['POST'])
@login_required
def get_diversity():
    if current_user.fake == 0:
        div = request.form['diversity']
        real = div
    elif current_user.fake == 1:
        div = 1
        real = request.form['diversity']
    else:
        div = 1
        real = 1
    div_final  = Diversity(diversity = div,  user_id = current_user.id, real = real)
    db.session.add(div_final)
    db.session.commit()
    return redirect(url_for('get_points'))

@app.route('/num_recommended', methods = ['POST'])
@login_required
def get_num_recommended():
    if current_user.fake == 0:
        number = request.form['num_recommended']
        real = number
    elif current_user.fake == 1:
        number = num_recommender
        real = request.form['num_recommended']
    else:
        number = num_recommender
        real = num_recommender
    number_rec = Num_recommended(num_recommended = number, user_id = current_user.id, real = real)
    db.session.add(number_rec)
    db.session.commit()
    return redirect(url_for('get_points'))

@app.route('/privacy_policy', methods = ['GET', 'POST'])
def privacy_policy():
    return render_template('privacy_policy.html')
