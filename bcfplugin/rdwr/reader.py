import sys
import os
import dateutil.parser
from zipfile import ZipFile
from xmlschema import XMLSchema
from uuid import UUID
from typing import List, Dict

if __name__ == "__main__":
    sys.path.insert(0, "../")
    print(sys.path)
import util as util
from util import debug, DEBUG
from rdwr.project import Project
from rdwr.uri import Uri as Uri
from rdwr.markup import (Comment, Header, HeaderFile, ViewpointReference, Markup)
from rdwr.topic import (Topic, BimSnippet, DocumentReference)
from rdwr.viewpoint import (Viewpoint, Component, Components, ViewSetupHints,
        ComponentColour, PerspectiveCamera, OrthogonalCamera, BitmapFormat,
        Bitmap)
from rdwr.threedvector import (Point, Line, Direction, ClippingPlane)

# BCF standard versions that can be read in
SUPPORTED_VERSIONS = ["2.1"]

# path to the extracted BCF file
# gets set by readBcfFile()
bcfDir = ""

if DEBUG:
    import pprint


def readFile(path: str):

    """
    Tries to open the supplied file (`path`) and returns the ZipFile object.
    If an exception is raised `None` is returned.
    """

    if not os.path.exists(str):
        raise ValueError

    file = None
    try:
        file = ZipFile(path)
    except Exception as e:
        util.printErr("The supplied BCF file ({}) could not be opened.\nError:\
                {}".format(path, str(e)))
        return None

    return file


def extractFileToTmp(zipFilePath: str):

    """
    Extracts the zipFile to the temporary directory of the system.
    """

    zipFile = ZipFile(zipFilePath)

    tmpDir = util.getSystemTmp()
    extractionPath = os.path.join(tmpDir, os.path.basename(zipFilePath))

    debug("reader.extractFileToTmp(): Extracting {} to {}".format(zipFile.filename, extractionPath))
    zipFile.extractall(extractionPath)
    return extractionPath


def getVersion(extrBcfPath: str, versionSchemaPath: str):

    """
    Tries to open `extrBcfPath`/bcf.version. If successful it parses it
    into a python dictonary and returns the content of the attribute
    `VersionId` of the element `Version`.

    If `bcf.version` was not found a ValueError is raised. If `bcf.version`
    does not parse against versionSchema then `None` is returned.
    """

    versionFileName = "bcf.version"
    versionFilePath = os.path.join(extrBcfPath, versionFileName)
    if not os.path.exists(versionFilePath):
        raise ValueError("{} was not found in the extracted zip archive {}."\
                "Make sure that you opened a correct bcf zip archive.".format(
                    versionFileName,
                    os.path.basename(extrBcfPath)))

    versionSchema = XMLSchema(versionSchemaPath)
    if not versionSchema.is_valid(versionFilePath):
        return None

    versionDict = versionSchema.to_dict(versionFilePath)
    return versionDict["@VersionId"]


def getFileListByExtension(topDir: str, extension: str):

    """
    Returns a list of files in the `topDir` directory that end with `extension`
    """

    fileList = [ f for f in os.listdir(topDir)
                    if os.path.isfile(os.path.join(topDir, f)) ]
    return list(filter(lambda f: f.endswith(extension), fileList))


def getOptionalFromDict(d: Dict, desiredValue: str, empty):

    """
    Returns `d[desiredValue]` if desiredValue is a key of `d`. Otherwise empty
    is returned
    """

    if desiredValue in d:
        return d[desiredValue]
    return empty


########## Object builder functions ##########
"""
Following, all functions prefixed with `build` fulfill the purpose of creating
an object of the class that is specified after `build`. So `buildX` cretes an
object of type `X`.
The data for the object is supplied (in most cases) through a python dictionary.
This dictionary was created by parsing an XML file against an accompanying XSD
through the library `xmlschema`. All functions that expect such a dictionary
further expect the dictonary to be the value of the key value pair that was
generated for the according node from the XML. To make things clearer here a
little example. We will start with the XML file, then show how it is represented
as dictionary by xmlschema and lastly showing what each `buildX` function
expects.

XML
------------------------------
<topNode>
    <comment></comment>
    <comment id=2><author>a@b.c<author></comment>
    <comment id=3></comment>
</topNode>
------------------------------

Python dictonary:
------------------------------
{
    'comment': [None,
                {'@id': 2, 'author': 'a@b.c'},
                {'@id': 3}
               ]
}

buildComment now expects an element of the list value of 'comment'. So either
 - None
 - {'@id': 2, 'author': 'a@b.c'}
 - {'@id': 3}

------------------------------

Note how the keys corresponding to attributes are prefixed
with `@`.

The other type of build functions expect a path to a file. These can be
considered as somewhat top-level `build` functions. They receive the path to an
xml file, as well as a path to the corresponding XSD. They then call the lower
level `build` functions to generate objects of the nodes, if they are complex
enough.
"""

def buildProject(projectFilePath: str, projectSchema: str):

    if projectFilePath is None or projectSchema is None:
        return None
    if not os.path.exists(projectFilePath):
        return None
    if not os.path.exists(projectSchema):
        return None

    schema = XMLSchema(projectSchema)
    (projectDict, errors) = schema.to_dict(projectFilePath, validation="lax")
    util.printErrorList([ err.message for err in errors ])

    # can do that because the project file is valid and ProjectId is required
    # by the schema
    pId = UUID(projectDict["Project"]["@ProjectId"])
    pName = str()
    pExtensionSchema = str()
    if "Name" in projectDict["Project"]:
        pName = projectDict["Project"]["Name"]
    if "ExtensionSchema" in projectDict:
        pExtensionSchema = projectDict["ExtensionSchema"]

    p = Project(pId, pName, pExtensionSchema)
    return p


def buildComment(commentDict: Dict):

    id = UUID(commentDict["@Guid"])
    commentDate = dateutil.parser.parse(commentDict["Date"]) # parse ISO 8601 datetime
    commentAuthor = commentDict["Author"]

    modifiedAuthor = getOptionalFromDict(commentDict, "ModifiedAuthor", "")
    modifiedDate = getOptionalFromDict(commentDict, "ModifiedDate", None)
    if modifiedDate is not None:
        modifiedDate = dateutil.parser.parse(modifiedDate)

    commentString = commentDict["Comment"]

    viewpointRef = getOptionalFromDict(commentDict, "Viewpoint", None)
    if viewpointRef:
        viewpointRef = ViewpointReference(id=UUID(viewpointRef["@Guid"]))

    comment = Comment(id, commentDate, commentAuthor,
            commentString, viewpointRef, modifiedDate, modifiedAuthor)

    return comment


def buildBimSnippet(snippetDict: Dict):

    reference = Uri(snippetDict["Reference"])
    referenceSchema = Uri(snippetDict["ReferenceSchema"])
    snippetType = snippetDict["@SnippetType"]
    isExternal = getOptionalFromDict(snippetDict, "@isExternal", False)

    bimSnippet = BimSnippet(snippetType, isExternal, reference, referenceSchema)

    return bimSnippet


def buildDocRef(docDict: Dict):

    docUri = getOptionalFromDict(docDict, "ReferencedDocument", None)
    if docUri: # envelope a uri string into an object of Uri
        docUri = Uri(docUri)

    docName = getOptionalFromDict(docDict, "Description", None)
    docId = getOptionalFromDict(docDict, "@Guid", None)
    if docId: #envelope a guid in an UUID object
        docId = UUID(docId)

    docExternal = getOptionalFromDict(docDict, "@isExternal", False)

    return DocumentReference(docId, docExternal, docUri, docName)


def buildTopic(topicDict: Dict):

    id = UUID(topicDict["@Guid"])
    title = topicDict["Title"]

    topicDate = dateutil.parser.parse(topicDict["CreationDate"])
    topicAuthor = topicDict["CreationAuthor"]

    topicStatus = getOptionalFromDict(topicDict, "@TopicStatus", "")
    topicType = getOptionalFromDict(topicDict, "@TopicType", "")
    topicPriority = getOptionalFromDict(topicDict, "Priority", "")

    modifiedDate = getOptionalFromDict(topicDict, "ModifiedDate", None)
    if modifiedDate is not None:
        modifiedDate = dateutil.parser.parse(modifiedDate)
    modifiedAuthor = getOptionalFromDict(topicDict, "ModifiedAuthor", "")

    index = getOptionalFromDict(topicDict, "Index", -1)
    dueDate = getOptionalFromDict(topicDict, "DueDate", None)
    if dueDate is not None:
        dueDate = dateutil.parser.parse(dueDate)

    assignee = getOptionalFromDict(topicDict, "AssignedTo", "")
    stage = getOptionalFromDict(topicDict, "Stage", "")
    description = getOptionalFromDict(topicDict, "Description", "")

    bimSnippet = None
    if "BimSnippet" in topicDict:
        bimSnippet = buildBimSnippet(topicDict["BimSnippet"])

    labelList = getOptionalFromDict(topicDict, "Labels", [])

    docRefList = getOptionalFromDict(topicDict, "DocumentReference", [])
    docRefs = [ buildDocRef(docRef) for docRef in docRefList ]

    relatedList = getOptionalFromDict(topicDict, "RelatedTopic", [])
    relatedTopics = [ UUID(relTopic["@Guid"]) for relTopic in relatedList ]

    referenceLinks = getOptionalFromDict(topicDict, "ReferenceLink", [])

    topic = Topic(id, title, topicDate, topicAuthor,
            topicType, topicStatus, referenceLinks,
            docRefs, topicPriority, index,
            labelList, modifiedDate, modifiedAuthor, dueDate,
            assignee, description, stage,
            relatedTopics, bimSnippet)

    return topic


def buildFile(fileDict):

    filename = getOptionalFromDict(fileDict, "Filename", "")
    filedate = getOptionalFromDict(fileDict, "Date", None)
    if filedate:
        filedate = dateutil.parser.parse(filedate)

    reference = getOptionalFromDict(fileDict, "Reference", "")
    if reference:
        reference = Uri(reference)

    ifcProjectId = getOptionalFromDict(fileDict, "@IfcProject", "")
    if ifcProjectId:
        ifcProjectId = ifcProjectId

    ifcSpatialStructureElement = getOptionalFromDict(fileDict,
            "@IfcSpatialStructureElement", "")
    if ifcSpatialStructureElement:
        ifcSpatialStructureElement = ifcSpatialStructureElement

    isExternal = getOptionalFromDict(fileDict, "@isExternal", True)

    headerfile = HeaderFile(ifcProjectId,
            ifcSpatialStructureElement,
            isExternal,
            filename,
            filedate,
            reference)

    return headerfile


def buildHeader(headerDict):

    filelist = getOptionalFromDict(headerDict, "File", list())
    files = [ buildFile(f) for f in filelist if f is not None ]

    header = Header(files)

    return header


def buildViewpointReference(viewpointDict):

    id = UUID(viewpointDict["@Guid"])
    viewpointFile = getOptionalFromDict(viewpointDict, "Viewpoint", None)
    if viewpointFile:
        viewpointFile = Uri(viewpointFile)

    snapshotFile = getOptionalFromDict(viewpointDict, "Snapshot", None)
    if snapshotFile:
        snapshotFile = Uri(snapshotFile)

    # -1 denotes a missing index value
    index = getOptionalFromDict(viewpointDict, "Index", -1)

    vpReference = ViewpointReference(id, viewpointFile, snapshotFile, index)

    return vpReference


def buildMarkup(markupFilePath: str, markupSchemaPath: str):

    markupSchema = XMLSchema(markupSchemaPath)
    (markupDict, errors) = markupSchema.to_dict(markupFilePath, validation="lax")
    util.printErrorList([ err.message for err in errors ])

    commentList = getOptionalFromDict(markupDict, "Comment", list())
    comments = [ buildComment(comment) for comment in commentList ]

    topicDict = markupDict["Topic"]
    topic = buildTopic(topicDict)

    headerDict = getOptionalFromDict(markupDict, "Header", None)
    header = None
    # there may be instances that define an empty header element
    if headerDict and len(headerDict) > 0:
        header = buildHeader(headerDict)

    viewpointList = getOptionalFromDict(markupDict, "Viewpoints", list())
    viewpoints = [ buildViewpointReference(vpDict)
                    for vpDict in viewpointList ]

    markup = Markup(topic, header, comments, viewpoints)

    # Add the right viewpoint references to each comment
    for comment in comments:
        if comment.viewpoint:
            cViewpointRefGuid = comment.viewpoint.xmlId
            viewpointRef = markup.getViewpointRefByGuid(cViewpointRefGuid)
            comment.viewpoint = viewpointRef

    return markup


def buildViewSetupHints(vshDict: Dict):

    spacesVisible = getOptionalFromDict(vshDict, "@SpacesVisible", False)
    spaceBoundariesVisible = getOptionalFromDict(vshDict,
            "@SpaceBoundariesVisible", False)
    openingsVisible = getOptionalFromDict(vshDict, "@OpeningsVisible", False)

    vsh = ViewSetupHints(openingsVisible, spacesVisible,
            spaceBoundariesVisible)
    return vsh


def buildComponent(componentDict: Dict):

    id = getOptionalFromDict(componentDict, "@IfcGuid", None) # is no UUID

    authoringToolId = getOptionalFromDict(componentDict,
            "AuthoringToolId", "")

    originatingSystem = getOptionalFromDict(componentDict,
            "OriginatingSystem", "")

    component = Component(id, originatingSystem, authoringToolId)
    return component


def buildComponentColour(ccDict: Dict):

    colour = getOptionalFromDict(ccDict, "@Color", None)
    colourComponents = list()
    cc = None
    if colour: # if a colour is defined then at least one component has to exist
        colourComponentList = [ buildComponent(cp)
                                for cp in ccDict["Component"] ]
        cc = ComponentColour(colour, colourComponentList)

    return cc


def buildComponents(componentsDict: Dict):

    vshDict = getOptionalFromDict(componentsDict, "ViewSetupHints", None)
    vsh = None
    if vshDict:
        vsh = buildViewSetupHints(vshDict)

    componentDict = getOptionalFromDict(componentsDict, "Selection", None)
    sel = list()
    if componentDict:
        componentList = componentDict["Component"]
        sel = [ buildComponent(cpDict) for cpDict in componentList ]

    visibilityDict = componentsDict["Visibility"]
    defaultVisibility = getOptionalFromDict(visibilityDict,
            "@DefaultVisibility", True)

    exceptionDict = getOptionalFromDict(visibilityDict, "Exceptions", None)
    exceptions = list()
    if exceptionDict:
        exceptionList = exceptionDict["Component"] # at least one element has to be present
        exceptions = [ buildComponent(cp) for cp in exceptionList ]

    colourComponentDict = getOptionalFromDict(componentsDict, "Coloring", None)
    componentColours = list()
    if colourComponentDict:
        colourComponentList = colourComponentDict["Color"] # at least one color is required
        componentColours = [ buildComponentColour(ccDict)
                                for ccDict in colourComponentList ]

    components = Components(defaultVisibility, exceptions, sel,
            vsh, componentColours)

    return components


def buildPoint(pointDict: Dict):

    return Point(pointDict["X"], pointDict["Y"], pointDict["Z"])


def buildDirection(dirDict: Dict):

    return Direction(dirDict["X"], dirDict["Y"], dirDict["Z"])


def buildOrthogonalCamera(oCamDict: Dict):

    camViewpoint = buildPoint(oCamDict["CameraViewPoint"])
    camDirection = buildDirection(oCamDict["CameraDirection"])
    camUpVector = buildDirection(oCamDict["CameraUpVector"])
    vWorldScale = oCamDict["ViewToWorldScale"]

    cam = OrthogonalCamera(camViewpoint, camDirection, camUpVector, vWorldScale)

    return cam


def buildPerspectiveCamera(pCamDict: Dict):

    camViewpoint = buildPoint(pCamDict["CameraViewPoint"])
    camDirection = buildDirection(pCamDict["CameraDirection"])
    camUpVector = buildDirection(pCamDict["CameraUpVector"])
    fieldOfView = pCamDict["FieldOfView"] # [0, 360] in version 2.1

    cam = PerspectiveCamera(camViewpoint, camDirection, camUpVector,
            fieldOfView)

    return cam


def buildLine(lineDict: Dict):

    start = buildPoint(lineDict["StartPoint"])
    end = buildPoint(lineDict["EndPoint"])

    line = Line(start, end)

    return line


def buildClippingPlane(clipDict: Dict):

    location = buildPoint(clipDict["Location"])
    direction = buildDirection(clipDict["Direction"])

    cPlane = ClippingPlane(location, direction)

    return cPlane


def buildBitmap(bmDict: Dict):

    bmFormatStr = bmDict["Bitmap"] # either JPG or PNG
    bmFormat = BitmapFormat.PNG if bmFormatStr == "PNG" else BitmapFormat.JPG

    reference = bmDict["Reference"]
    location = buildPoint(bmDict["Location"])
    normal = buildDirection(bmDict["Normal"])
    up = buildDirection(bmDict["Up"])
    height = bmDict["Height"]

    bitmap = Bitmap(bmFormat, reference, location, normal, up, height)

    return bitmap


def buildViewpoint(viewpointFilePath: str, viewpointSchemaPath: str):

    """
    Builds an object of type viewpoint.
    """

    vpSchema = XMLSchema(viewpointSchemaPath)
    (vpDict, errors) = vpSchema.to_dict(viewpointFilePath, validation="lax")
    util.printErrorList([ str(err) for err in errors ])

    id = UUID(vpDict["@Guid"])

    componentsDict = getOptionalFromDict(vpDict, "Components", None)
    components = None
    if componentsDict:
        components = buildComponents(componentsDict)

    oCamDict = getOptionalFromDict(vpDict, "OrthogonalCamera", None)
    oCam = None
    if oCamDict:
        oCam = buildOrthogonalCamera(oCamDict)

    pCamDict = getOptionalFromDict(vpDict, "PerspectiveCamera", None)
    pCam = None
    if pCamDict:
        pCam = buildPerspectiveCamera(pCamDict)

    linesDict = getOptionalFromDict(vpDict, "Lines", None)
    lines = list()
    if linesDict:
        linesList = getOptionalFromDict(linesDict, "Line", list())
        lines = [ buildLine(line) for line in linesList ]

    clippingPlaneDict = getOptionalFromDict(vpDict, "ClippingPlanes", None)
    clippingPlanes = list()
    if clippingPlaneDict:
        clippingPlaneList = getOptionalFromDict(clippingPlaneDict,
                "ClippingPlane", list())
        clippingPlanes = [ buildClippingPlane(clipDict)
                            for clipDict in clippingPlaneList ]

    bitmapList = getOptionalFromDict(vpDict, "Bitmap", list())
    bitmaps = [ buildBitmap(bmDict) for bmDict in bitmapList ]

    viewpoint = Viewpoint(id, components, oCam,
            pCam, lines, clippingPlanes, bitmaps)

    return viewpoint


def validateFile(validateFilePath: str,
        schemaPath: str,
        bcfFile: str):

    """
    Validates `validateFileName` against the XSD file referenced by
    `schemaPath`. If successful an empty string is returned, else an error
    string is returned.
    """

    schema = XMLSchema(schemaPath)
    try:
        schema.validate(validateFilePath)
    except Exception as e:
        # get parent directory of file, useful for the user if the file is a
        # markup.bcf file inside some topic
        parentDir = os.path.abspath(os.path.join(validateFilePath, os.pardir))
        return "{} file inside {} of {} could not be validated against"\
                " {}\nError:{}".format(validateFilePath, parentDir, bcfFile,
                    os.path.basename(schemaPath), str(e))

    return ""


def readBcfFile(bcfFile: str):

    """
    Reads the bcfFile into the memory. Before each file is parsed into the class
    structure it gets validated against its corresponding XSD file.
    If parsing went successful then a value other than a object of type Project
    is returned.
    """

    global bcfDir

    tmpDir = util.getSystemTmp()
    (projectSchemaPath, extensionsSchemaPath,\
        markupSchemaPath, versionSchemaPath,\
        visinfoSchemaPath) = util.copySchemas(tmpDir)
    # extensionsSchemaPath is optional and currently not used => does not need
    # to be downloaded.
    if (projectSchemaPath is None or
            markupSchemaPath is None or
            versionSchemaPath is None or
            visinfoSchemaPath is None):
        util.printErr("One or more schema files could not be downloaded!"\
                "Please try again in a few moments")
        return None

    bcfExtractedPath = extractFileToTmp(bcfFile)

    # before a file gets read into memory it needs to get validated (i.e.:
    # before the corresponding build* function is called, validate with
    # xmlschema)
    ### Check version ###
    versionFilePath = os.path.join(bcfExtractedPath, "bcf.version")
    if not os.path.exists(versionFilePath):
        util.printErr("No bcf.version file found in {}. This file is not optional.",
                file=sys.stderr)
        return None
    error = validateFile(versionFilePath, versionSchemaPath, bcfFile)
    if error != "":
        pprint.pprint(error, file=sys.stderr)
        return None
    version = getVersion(bcfExtractedPath, versionSchemaPath)
    if version not in SUPPORTED_VERSIONS:
        pprint.pprint("BCF version {} is not supported by this plugin. Supported"\
                "versions are: {}".format(version, SUPPORTED_VERSIONS),
                file=sys.stderr)
        return None

    ### Validate project and build ###
    # project.bcfp is optional, but it is necessary for the data model
    proj = Project(UUID(int=0))
    projectFilePath = os.path.join(bcfExtractedPath, "project.bcfp")
    if os.path.exists(projectFilePath):
        error = validateFile(projectFilePath, projectSchemaPath, bcfFile)
        if error != "":
            debug("{} is not completely valid. Some parts won't be available."\
                    " Following the error message:\n{}".format(projectFilePath,
                        error))
        proj = buildProject(projectFilePath, projectSchemaPath)

    ### Iterate over the topic directories ###
    topicDirectories = util.getDirectories(bcfExtractedPath)
    debug(topicDirectories)
    for topic in topicDirectories:
        ### Validate all viewpoint files in the directory, and build them ###
        topicDir = os.path.join(bcfExtractedPath, topic)

        markupFilePath = os.path.join(topicDir, "markup.bcf")
        debug("reader.readBcfFile(): looking into topic {}".format(topicDir))
        error = validateFile(markupFilePath, markupSchemaPath, bcfFile)
        if error != "":
            util.printErr("{} does not comply with the standard of versions {}."\
                   " Some parts won't be available."\
                   " Error:\n{}".format(markupFilePath, SUPPORTED_VERSIONS,
                        error))
        markup = buildMarkup(markupFilePath, markupSchemaPath)

        # generate a viewpoint object for all viewpoints listed in the markup
        # object and add them to the ViewpointReference object (`viewpoint`)
        # inside markup
        for vpRef in markup.viewpoints:
            vpPath = os.path.join(topicDir, vpRef.file.uri)
            try:
                # if some required element was not found, indicated by a key
                # error then skip the viewpoint
                vp = buildViewpoint(vpPath, visinfoSchemaPath)
            except KeyError as err:
                util.printErr("{} is required in a viewpoint file."
                    " Viewpoint {}/{} is skipped"\
                        "".format(str(err), topic, vpRef.file))
                continue
            else:
                vpRef.viewpoint = vp

        markup.containingObject = proj
        # add the finished markup object to the project
        proj.topicList.append(markup)

    bcfDir = bcfExtractedPath
    debug("reader.readBcfFile(): BCF file is open at {}".format(bcfDir))
    return proj


if __name__ == "__main__":
    argFile = "test_data/Issues_BIMcollab_Example.bcf"
    if len(sys.argv) >= 2:
        argFile = sys.argv[1]
    project = readBcfFile(argFile)
    print(project)