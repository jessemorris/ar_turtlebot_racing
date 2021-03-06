#!/usr/bin/env python

import rospy
from std_msgs.msg import String
import ros_numpy
from sensor_msgs.msg import Image, CameraInfo
import numpy as np
import math
from mesh_visualiser.srv import RequestModelView
from geometry_msgs.msg import Quaternion
from tf.transformations import quaternion_matrix, euler_from_quaternion, quaternion_from_euler, euler_matrix
import tf
import cv2
import time

class ObjectPlacement():

    def __init__(self):
        self.input_image_topic = rospy.get_param("object_placement/input_camera_topic")

        print(self.input_image_topic)


        rospy.wait_for_service('mesh_visualiser/model_view_bunny')

        self.model_view_service = rospy.ServiceProxy('mesh_visualiser/model_view_bunny',RequestModelView)
        self.tf_listener = tf.TransformListener()



        rospy.Subscriber(self.input_image_topic,Image,self.imageCallback, queue_size=1)

        self.pub = rospy.Publisher('output_overlayed_image', Image, queue_size=1)



        self.cv_image = None
        self.principal_point_x = 640/2
        self.principal_point_y = 480/2
        self.u0 = self.principal_point_x
        self.v0 = self.principal_point_y
        self.fx = 519.566467
        self.fy = 522.066406
        self.distortion_array = np.array([0.187523, -0.355696, 0.002719, -0.003771, 0.000000])

        #k1, k2, k3 is radial distortion
        #k4,k5 is tangential distortion
        self.k4 = self.distortion_array[0]
        self.k5 = self.distortion_array[1]
        self.k1 = self.distortion_array[2]
        self.k2 = self.distortion_array[3]
        self.k3 = self.distortion_array[4]

        #K = intrinsic matrix
        self.K = np.array([[519.566467, 0.000000, 313.837735, 0.000000],
            [0.000000, 522.066406, 248.386084, 0.000000],
            [0.000000, 0.000000, 1.000000, 0.000000]])





    # goes from x,y,z world to pixel frame
    def getPixelCoordinates(self, x_world, y_world, z_world, camera_translation, camera_rotation):
        #p = point in world frame [x,y,z,0]
        # x = 5
        # y = 5
        # z = 10
        world_frame_point = np.array([x_world,y_world,z_world,1])
        print("World frame")
        print(world_frame_point)

        # R = camera rotation matrix
        # T = camera translation matrix
        # R = np.identity(3)

        # T = np.array([[0],[0],[0]])

        #convert to correct form for matrix operations
        # print(camera_translation)
        # print(camera_rotation)
        camera_translation =  np.array([[camera_translation[0]],[camera_translation[1]],[camera_translation[2]]])
        camera_rotation = np.array([camera_rotation[0][:3],camera_rotation[1][:3],camera_rotation[2][:3]])
        print("Translation")
        print(camera_translation)
        print("Rotation")
        print(camera_rotation)





        camera_rotation = np.transpose(camera_rotation)

        # print(camera_rotation)
        # print(camera_translation)
        #extrinsic_matrix = [R', T'; 0,0,0,1]
        extrinsic_matrix = np.concatenate((camera_rotation,camera_translation),axis = 1)
        padding = np.array([[0,0,0,1]])

        # print(extrinsic_matrix)

        extrinsic_matrix = np.concatenate((extrinsic_matrix,padding))
        print(extrinsic_matrix)


        # test = np.matmul(K,extrinsic_matrix)

        camera_frame = np.matmul(np.matmul(self.K,extrinsic_matrix),np.transpose(world_frame_point))
        print(camera_frame)


        #these are the undistored points
        u = np.divide(camera_frame[0],camera_frame[2])
        v = np.divide(camera_frame[1],camera_frame[2])


        print("u {}".format(u))
        print("v {}".format(v))

        #u0 = principal_point x
        #v0 = principal_point y

        # fx = focal length x
        # fy = focal length y

        x = (u-self.u0)/self.fx
        y = (v-self.v0)/self.fy

        print(x, y)

        r = math.sqrt(x**2+y**2)

        #k1, k2, k3 is radial distortion
        #k4,k5 is tangential distortion
        xd = x*(1+self.k1*r**2 +self.k2*r**4 + self.k3*r**6) + 2*self.k4*x*y+self.k5*(r**2+2*x**2);
        yd = y*(1+self.k1*r**2 +self.k2*r**4 + self.k3*r**6)+self.k4*(r**2+2*y**2)+2*self.k5*x*y;

        #distorted pixel coordinates
        ud = self.fx*xd + self.u0
        vd= self.fy*yd + self.v0

        print(ud, vd)

        return [int(round(u)), int(round(v))]

    def overlay_image_alpha(self, img, img_overlay, pos, alpha_mask):
        """Overlay img_overlay on top of img at the position specified by
        pos and blend using alpha_mask.

        Alpha mask must contain values within the range [0, 1] and be the
        same size as img_overlay.
        """

        x, y = pos

        # Image ranges
        y1, y2 = max(0, y), min(img.shape[0], y + img_overlay.shape[0])
        x1, x2 = max(0, x), min(img.shape[1], x + img_overlay.shape[1])

        # Overlay ranges
        y1o, y2o = max(0, -y), min(img_overlay.shape[0], img.shape[0] - y)
        x1o, x2o = max(0, -x), min(img_overlay.shape[1], img.shape[1] - x)

        # Exit if nothing to do
        if y1 >= y2 or x1 >= x2 or y1o >= y2o or x1o >= x2o:
            return

        channels = img.shape[2]

        alpha = alpha_mask[y1o:y2o, x1o:x2o]
        alpha_inv = 1.0 - alpha

        for c in range(channels):
            img[y1:y2, x1:x2, c] = (alpha * img_overlay[y1o:y2o, x1o:x2o, c] +
                                    alpha_inv * img[y1:y2, x1:x2, c])
        return img



    def imageCallback(self,data):

        # returns image as a numpy array
        self.cv_image = ros_numpy.numpify(data)[... , :3][...,::-1]
        # self.cv_image = cv2.rotate(self.cv_image, cv2.ROTATE_180)
        # print(self.cv_image.shape)

        try:
            self.tf_listener.waitForTransform("rotated_map", "rotated_turtlebot",rospy.Time(), rospy.Duration(secs=4) )
            translation_turtlebot, rotation_turtlebot = self.tf_listener.lookupTransform("rotated_map", "rotated_turtlebot",rospy.Time(0))
            # print(translation_turtlebot)
            print("rotation_turtlebot")
            print(rotation_turtlebot)
        except Exception as e:
            rospy.logwarn("Could not get map to turtlbot image frame transform")
            return False

        try:
            self.tf_listener.waitForTransform("rotated_map", "rotated_bunny",rospy.Time(), rospy.Duration(secs=4) )
            translation_object, rotation_object = self.tf_listener.lookupTransform("rotated_bunny", "rotated_map",rospy.Time(0))
        except Exception as e:
            rospy.logwarn("Could not get map to bunny frame transform")
            return False

        # for each of the objects in the world frame
        x_world, y_world, z_world = translation_object

        # print(translation_object)

        # convert quaternion to rotation matrix
        # rotation_matrix = quaternion_matrix(rotation_turtlebot)
        # rotation_matrix = quaternion_matrix([rotation_turtlebot[3],
        #                                     rotation_turtlebot[0],
        #                                     rotation_turtlebot[1],
        #                                     rotation_turtlebot[2]])
        flipped_rotation = [rotation_turtlebot[3],
                            rotation_turtlebot[0],
                            rotation_turtlebot[1],
                            rotation_turtlebot[2]]
        euler = euler_from_quaternion(flipped_rotation)
        print("euler")
        print(np.array(euler)*180/np.pi)
        rotation_matrix = euler_matrix(euler[0], euler[1], euler[2])

        print(rotation_matrix)
        # rotation_matrix = np.identity(3)
        image_center_x, image_center_y = self.getPixelCoordinates(x_world,y_world, z_world,translation_turtlebot, rotation_matrix)


        print(image_center_x)
        print(image_center_y)

        image_center_x = image_center_x - 640/2 
        image_center_y = image_center_y - 480/2 

        # image_center_x = - image_center_x
        # image_center_y = - image_center_y

        print(image_center_x)
        print(image_center_y)
        

        # #testing
        # image_center_x = -100
        # image_center_y = -200

        #0, 0.7071068, 0, 0.7071068
        #  0, 0, 0.7071068, 0.7071068
        quaternion = Quaternion( -0.7071068, 0, 0, 0.7071068)
        time_start = time.time()
        response = self.model_view_service(quaternion)
        time_end =  time.time()

        print("Time {}".format(time_end - time_start))


        model_image = ros_numpy.numpify(response.image)[... , :4][...,::-1]
        alpha = model_image[:, :, 3] / 255.0


        b,g,r = cv2.split(self.cv_image)

        image_rgb = cv2.merge((r,g, b))

        result = self.overlay_image_alpha(image_rgb,model_image,(image_center_x, image_center_y), alpha )

        # print(model_image.shape)

        # h, w, c = self.cv_image.shape

        # model_image_translated = np.zeros(model_image.shape)

        # model_image_translated[image_center_y:image_center_y + model_image.shape[0], image_center_x:image_center_x+model_image.shape[1]] = model_image


        # result = np.zeros((h, w, 3), np.uint8)


        # # st = time()
        # alpha = model_image[:, :, 3] / 255.0
        # result[:, :, 0] = (1. - alpha) * self.cv_image[:, :, 0] + alpha * model_image_translated[:, :, 0]
        # result[:, :, 1] = (1. - alpha) * self.cv_image[:, :, 1] + alpha * model_image_translated[:, :, 1]
        # result[:, :, 2] = (1. - alpha) * self.cv_image[:, :, 2] + alpha * model_image_translated[:, :, 2]
        # # end = time() - st
        # # print(end)


        output_image_message = ros_numpy.msgify(Image, result,encoding = '8UC3')
        # cv2.imshow("result", result)
        # cv2.waitKey(0)
        # cv2.destroyAllWindows()


        self.pub.publish(output_image_message)


if __name__ == '__main__':
    # listener()


    rospy.init_node('object_placement')
    obj = ObjectPlacement()

    rospy.spin()
