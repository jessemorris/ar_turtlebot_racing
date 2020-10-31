#include <ros/ros.h>
#include <nodelet/loader.h>

#include <cv_bridge/cv_bridge.h>
#include <sensor_msgs/image_encodings.h>
#include <sensor_msgs/Image.h>
#include <opencv2/core.hpp>
#include <opencv2/videoio.hpp>
#include <opencv2/highgui.hpp>
#include <image_transport/image_transport.h>
#include <iostream>
#include <stdio.h>


#include <string>

int main(int argc, char **argv)
{
    ros::init(argc, argv, "psmove_camera");
    ros::NodeHandle n;

    std::string output_video_topic;
    n.getParam("psmove_camera/image_topic", output_video_topic);

    int device_id;
    n.getParam("psmove_camera/device_id", device_id);

    image_transport::ImageTransport it(n);
    image_transport::Publisher pub_img = it.advertise(output_video_topic, 1);

    cv::VideoCapture cap;

    if (!cap.open(device_id)) {
        ROS_ERROR("Camera failed to open");
        return -1;
    }

    cv::Mat image;
    sensor_msgs::ImagePtr img_msg; // >> message to be sent

    while (ros::ok()) {
        cap.read(image);

        if (image.empty()) {
            ROS_WARN("Frame was empty");
        }
        else {
            img_msg = cv_bridge::CvImage(std_msgs::Header(), "bgr8", image).toImageMsg();
            pub_img.publish(img_msg);
        }
        ros::spinOnce();

    }
    return 0;
}