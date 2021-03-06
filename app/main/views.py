from . import main
from flask import Blueprint, redirect, render_template,request,safe_join,send_from_directory,request,Response,send_file
from flask import request, url_for,flash
from flask_user import current_user, login_required, roles_accepted
from app import db,app,databases,module_methods
from app.databases.user_models import UserProfileForm,User
from app.decorators import admin_required,permission_required,logged_in_required
from app.ngs.project import GenericObject,get_project,get_main_project_types
from app.ngs.genome import get_genomes
from flask_cors import cross_origin

import ujson,sys,re,mimetypes


#***********GENERAL PAGES**********************
@main.route('/')
def home_page():
    return render_template(app.config["HOME_PAGE"])


@main.route("/manage_projects")
def manage_projects():
    return render_template("projects/manage_projects.html")
    

@main.route("/projects/<project_type>/home")
def project_home_page(project_type):
    not_allow_other = app.config["MLV_PROJECTS"][project_type].get("not_allow_other")
        
          
    return render_template("{}/home.html".format(project_type),
                           project_type=project_type,
                           genomes=get_genomes(not_allow_other))
    

@main.route("/modules/<module>/home")    
def module_home_page(module):
    if not app.config["MODULE_INFO"][module]["is_public"]:
        if not current_user.is_authenticated or not current_user.has_permission("view_module",module):
            return refuse_permission()
    data=None
    meth = module_methods.get(module)
    if meth:
        data=meth(current_user)
    return render_template("{}.html".format(module),**data)
            
    
    


#********************************************************************
#***The following should be overidden by directives in the webserver
#*********************************************************************

'''calls to static module files are rerouted
to the module's static folder - can do this at the server level 
e.g with nginx:-
location ~  /(.*)/static/(.*) {
    alias /<app_root>/modules/$1/static/$2;
}'''
@main.route("/<project>/static/<path:path>")
def test_url(project,path):
   f= safe_join("modules",project,"static",path)
   return send_from_directory(app.root_path,f)


@main.route("/data/temp/<path:path>")
def temp_url(path):
    return send_from_directory(app.config["TEMP_FOLDER"],path)
   
@main.route("/data/<path:path>")
def image_route(path):
    if path.endswith(".png"):
        return send_from_directory(app.config["DATA_FOLDER"],path)

@main.route("/tracks/<path:path>")
def send_track(path):
    file_name =safe_join(app.config["TRACKS_FOLDER"],path)
    range_header = request.headers.get('Range', None)
    
    if not range_header:
        return send_file(file_name)
    
    file =open(file_name,"rb")
    size = sys.getsizeof(file)
    byte1, byte2 = 0, None

    m = re.search('(\d+)-(\d*)', range_header)
    g = m.groups()

    if g[0]:
        byte1 = int(g[0])
    if g[1]:
        byte2 = int(g[1])

    length = size - byte1
    if byte2 is not None:
        length = byte2 - byte1 + 1

    file.seek(byte1)
    data = file.read(length)

    rv = Response(data,
                  206,
                  mimetype=mimetypes.guess_type(file_name)[0],
                  direct_passthrough=True)
    rv.headers.add('Content-Range', 'bytes {0}-{1}/{2}'.format(byte1, byte1 + length - 1, size))
    rv.headers.add('Accept-Ranges', 'bytes')
    file.close()
    return rv

#*********************************************************************
    
@main.route("/projects/<type>/<int:project_id>")
def project_page(type,project_id):
    p = get_project(project_id)
    if not  p.has_view_permission(current_user):
        return refuse_permission()
    template,args = p.get_template(request.args)
    all_args={
        "project_id":project_id,
        "project_name":p.name, 
        "project_type":type,
        "description":p.description     
    }
    all_args.update(args)
    return render_template(template,**all_args)
   
@main.route("/projects")
def projects():
    return render_template("projects/projects.html")



#***********JOBS*************************


@main.route("/jobs/jobs_panel")
@admin_required
def jobs_panel():
    return render_template('admin/view_jobs.html')


@main.route("/admin/users_panel")
@admin_required
def users_panel():
    return render_template('admin/view_users.html')


@main.route("/jobs/my_jobs")
@logged_in_required
def my_jobs():
    return render_template('admin/view_jobs.html',my_jobs=True)



@main.route("/general/get_info")
def get_general_info():
    return ujson.dumps({
         "genomes":get_genomes(),
         "projects":get_main_project_types()
    })
   
   
@main.route("/general/get_jobs_projects")
@logged_in_required
def get_jobs_projects():
    sql = "SELECT COUNT(status) FILTER(WHERE status='failed') AS failed, COUNT(status) FILTER(WHERE status<>'failed') AS running FROM jobs WHERE user_id={} AND status <> 'complete'".format(current_user.id)
    job_info = databases["system"].execute_query(sql)[0]
    sql = "SELECT COUNT(*) AS num FROM projects WHERE owner={} AND is_deleted=false AND type = ANY (%s)".format(current_user.id)
    projects=databases['system'].execute_query(sql,(app.config["MLV_MAIN_PROJECTS"],))[0]['num']
    return ujson.dumps({"projects":projects,"jobs":{"running":job_info['running'],"failed":job_info['failed']}})
    
@main.route("/browser_view/<int:project_id>/<int:view_id>")
@cross_origin()
def browser_view(project_id,view_id):
    return render_template("pages/genome_browser.html",project_id=project_id,view_id=view_id)






#********Helper Methods***********************************
def refuse_permission():
    if not current_user.is_authenticated:
        flash("You need to be logged in and have permission","error")
        return redirect(url_for('user.login', next=request.url))
    else:
        flash("You do not have permission for " +request.url ,"error")
        return redirect(url_for('main.home_page'))
